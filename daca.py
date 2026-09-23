import argparse
from pathlib import Path
import json
import os
import time
from contextlib import contextmanager
import threading
from dataclasses import dataclass, field, asdict, fields, MISSING
import sys


SCRIPT_DIR = Path(__file__).parent
FILE = "changelog.json"
LOCK = "changelog.lock"
STALE = 10            # 秒，超过视为残留锁；写 changelog 是毫秒级，10 秒足够
WAIT_SECONDS = 3.0    # 拿不到锁的总等待
WAIT_INTERVAL = 0.05

GITIGNORE = ".gitignore"

IGNORED = ["changelog.json", "changelog.lock", "changelog.json.tmp"]


_local = threading.local()


AUTHORS = {"功能实现者", "功能审查者"}
STATUSES = {"待审查", "待实现", "已通过", "需用户裁决"}
CONCLUSIONS = {"无", "通过", "不通过", "需用户裁决"}
JUDGEMENTS = {"无", "接受", "驳回", "需用户裁决"}

LEGAL = {
    ("功能实现者", "待审查"),
    ("功能审查者", "待实现"),
    ("功能审查者", "已通过"),
    ("功能审查者", "需用户裁决"),
}

LABELS = {
    "round": "轮次",
    "author": "作者",
    "status": "状态",
    "conclusion": "结论",
    "scope": "范围",
    "changes": "变更",
    "issues": "发现的问题",
    "mismatches": "与期望不一致",
    "suggestions": "改进建议",
    "blockers": "阻塞问题",
    "no_fix_reasons": "不修复理由",
    "rejection_judgement": "对不修复理由的判断",
    "judgement_note": "判断说明",
}


class InvalidField(ValueError):
    def __init__(self, field, value, allowed):
        self.field = field
        self.value = value
        self.allowed = allowed
        super().__init__(f"{field}={value!r} 非法，允许: {allowed}")


class CorruptChangelog(ValueError):
    pass


class AlternateError(ValueError):
    def __init__(self, prev, author):
        self.prev = prev
        self.author = author
        super().__init__(f"上一条作者也是 {author}，轮转未推进")


@dataclass(slots=True, kw_only=True)
class ChangeLog:
    round: int
    author: str
    status: str
    conclusion: str = "无"
    scope: str = ""
    changes: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    no_fix_reasons: list[str] = field(default_factory=list)
    rejection_judgement: str = "无"
    judgement_note: str = "无"

    def __post_init__(self):
        if self.author not in AUTHORS:
            raise InvalidField("author", self.author, sorted(AUTHORS))
        if self.status not in STATUSES:
            raise InvalidField("status", self.status, sorted(STATUSES))
        if self.conclusion not in CONCLUSIONS:
            raise InvalidField("conclusion", self.conclusion, sorted(CONCLUSIONS))
        if self.rejection_judgement not in JUDGEMENTS:
            raise InvalidField("rejection_judgement", self.rejection_judgement, sorted(JUDGEMENTS))
        if (self.author, self.status) not in LEGAL:
            allowed = [f"{a}+{s}" for a, s in sorted(LEGAL)]
            raise InvalidField("author+status", f"{self.author}+{self.status}", allowed)


_FIELD_NAMES = {f.name for f in fields(ChangeLog)}
_REQUIRED = {"round", "author", "status"}
_FIELD_DEFAULTS = {}
for _f in fields(ChangeLog):
    if _f.default is not MISSING:
        _FIELD_DEFAULTS[_f.name] = _f.default
    elif _f.default_factory is not MISSING:
        _FIELD_DEFAULTS[_f.name] = _f.default_factory()


def _held_depth():
    return getattr(_local, "depth", 0)


def _lock_path() -> Path:
    return SCRIPT_DIR / LOCK


def _is_stale() -> bool:
    try:
        st = _lock_path().stat()
    except OSError:
        return True
    return time.time() - st.st_mtime > STALE


def _break_stale():
    lock = _lock_path()
    tmp = lock.with_name(f"{lock.name}.{os.getpid()}.stale")
    try:
        os.rename(lock, tmp)
    except OSError:
        return
    try:
        os.unlink(tmp)
    except OSError:
        pass


def _try_acquire() -> bool:
    lock = _lock_path()
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except PermissionError:
        return False
    try:
        os.write(fd, f"{os.getpid()} {time.time()}".encode())
    except OSError:
        os.close(fd)
        try:
            os.unlink(lock)
        except OSError:
            pass
        raise
    os.close(fd)
    return True


def _acquire():
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        if _try_acquire():
            return
        if _is_stale():
            _break_stale()
        time.sleep(WAIT_INTERVAL)
    raise TimeoutError("获取锁超时")


def _release():
    lock = _lock_path()
    try:
        pid_str, _ = lock.read_text(encoding="utf-8").split()
        if int(pid_str) != os.getpid():
            return
    except (OSError, ValueError):
        return
    try:
        os.unlink(lock)
    except OSError:
        pass


@contextmanager
def changelog_lock():
    if _held_depth() > 0:
        # 同一线程重入：只加计数，不真正再抢
        _local.depth += 1
        try:
            yield
        finally:
            _local.depth -= 1
        return

    _acquire()
    _local.depth = 1
    try:
        yield
    finally:
        _local.depth = 0
        _release()


def _load_rounds(path: Path) -> list[ChangeLog]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise CorruptChangelog(f"文件无法读取或不是合法 JSON: {e}") from e
    if not isinstance(data, list):
        raise CorruptChangelog(f"顶层应为数组，实为 {type(data).__name__}")
    rounds = []
    for i, r in enumerate(data):
        try:
            rec = ChangeLog(**r)
        except InvalidField as e:
            raise CorruptChangelog(f"第 {i+1} 条记录 {e.field} 非法: {e.value!r}") from e
        except TypeError as e:
            # ChangeLog(**r) 的唯一失败路径是字段缺失或多余；
            # 若 __post_init__ 将来引入其他 TypeError 来源，需收窄这里。
            raise CorruptChangelog(f"第 {i+1} 条记录字段缺失或多余: {e}") from e
        expected = i + 1
        if rec.round != expected:
            raise CorruptChangelog(f"第 {i+1} 条记录 round 应为 {expected}，实为 {rec.round}")
        if rounds and rounds[-1].author == rec.author:
            raise CorruptChangelog(
                f"第 {i+1} 条记录作者与第 {i} 条相同: {rec.author}，轮转未推进"
            )
        rounds.append(rec)
    return rounds


def last_round() -> ChangeLog | None:
    with changelog_lock():
        path = SCRIPT_DIR / FILE
        rounds = _load_rounds(path)
    return rounds[-1] if rounds else None


def list_rounds(limit: int) -> list[ChangeLog]:
    with changelog_lock():
        path = SCRIPT_DIR / FILE
        rounds = _load_rounds(path)
    if limit > 0:
        return rounds[-limit:]
    return rounds


def append(**fields) -> ChangeLog:
    with changelog_lock():
        path = SCRIPT_DIR / FILE
        rounds = _load_rounds(path)
        record = ChangeLog(round=len(rounds) + 1, **fields)
        if rounds and rounds[-1].author == record.author:
            raise AlternateError(rounds[-1], record.author)
        rounds.append(record)
        _write_rounds(path, [asdict(r) for r in rounds])
        return record


def _write_rounds(path: Path, raw: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(raw, ensure_ascii=False, indent=2) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_raw(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise CorruptChangelog(f"文件无法读取或不是合法 JSON，fix 无法处理: {e}") from e
    if not isinstance(data, list):
        raise CorruptChangelog(f"顶层应为数组，实为 {type(data).__name__}，fix 无法处理")
    for i, r in enumerate(data):
        if not isinstance(r, dict):
            raise CorruptChangelog(f"第 {i+1} 条记录不是对象，fix 无法处理")
    return data


def _plan_fixes(data: list[dict]) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    result: list[dict] = []
    for i, raw in enumerate(data):
        idx = i + 1
        r = dict(raw)

        extra = [k for k in r if k not in _FIELD_NAMES]
        if extra:
            notes.append(f"第 {idx} 条: 删除多余字段 {extra}")
            r = {k: v for k, v in r.items() if k in _FIELD_NAMES}

        missing_required = [k for k in _REQUIRED if k not in r]
        if missing_required:
            raise CorruptChangelog(
                f"第 {idx} 条记录缺少必填字段 {missing_required}，fix 无法处理"
            )

        missing_optional = [k for k in _FIELD_NAMES - _REQUIRED if k not in r]
        if missing_optional:
            notes.append(f"第 {idx} 条: 补默认值 {missing_optional}")
            for k in missing_optional:
                r[k] = _FIELD_DEFAULTS[k]

        try:
            ChangeLog(**r)
        except InvalidField as e:
            raise CorruptChangelog(
                f"第 {idx} 条记录 {e.field} 非法 ({e.value!r})，fix 不猜测语义，无法处理"
            ) from e

        if result and result[-1]["author"] == r["author"]:
            raise CorruptChangelog(
                f"第 {idx} 条记录作者与第 {idx-1} 条相同，fix 不猜测语义，无法处理"
            )

        result.append(r)

    current = [r["round"] for r in result]
    expected = list(range(1, len(result) + 1))
    if current != expected:
        notes.append(f"重编号 round 为 1..{len(result)}")
        for i, r in enumerate(result):
            r["round"] = i + 1

    return result, notes


def fix(yes: bool) -> None:
    with changelog_lock():
        path = SCRIPT_DIR / FILE
        data = _read_raw(path)
        if not data:
            print("changelog 为空，无需修复")
            return

        fixed, notes = _plan_fixes(data)
        if not notes:
            print("无需修复")
            return

        print("将执行以下修复:")
        for n in notes:
            print(f"  - {n}")

        if not yes:
            print("（dry-run，未写入。加 --yes 落盘）")
            return

        _write_rounds(path, fixed)
        _load_rounds(path)  # 自检
        print("修复完成")


def format_value(v):
    if isinstance(v, list):
        if not v:
            return " 无"
        return "\n" + "\n".join(f"  - {item}" for item in v)
    if v == "":
        return " 无"
    return f" {v}"


def ensure_gitignore():
    if SCRIPT_DIR.name != "dual_agent_collaboration_agreement":
        IGNORED.insert(0, "daca.py")
    path = SCRIPT_DIR / GITIGNORE
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        return
    lines = {line.strip() for line in existing.splitlines()}
    missing = [name for name in IGNORED if name not in lines]
    if not missing:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            for name in missing:
                f.write(name + "\n")
    except OSError:
        pass


def main():
    ensure_gitignore()

    parser = argparse.ArgumentParser(prog="daca.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("get", help="打印最后一条记录")

    list_p = sub.add_parser("list", help="列出最近的记录")
    list_p.add_argument("--line", type=int, default=10)

    add_p = sub.add_parser("add", help="追加一条记录")
    add_p.add_argument("--author")
    add_p.add_argument("--status")
    add_p.add_argument("--conclusion", default="无")
    add_p.add_argument("--scope", default="")
    add_p.add_argument("--change", action="append", default=[], dest="changes")
    add_p.add_argument("--issue", action="append", default=[], dest="issues")
    add_p.add_argument("--mismatch", action="append", default=[], dest="mismatches")
    add_p.add_argument("--suggestion", action="append", default=[], dest="suggestions")
    add_p.add_argument("--blocker", action="append", default=[], dest="blockers")
    add_p.add_argument("--no-fix-reason", action="append", default=[], dest="no_fix_reasons")
    add_p.add_argument("--rejection-judgement", default="无")
    add_p.add_argument("--judgement-note", default="无")

    fix_p = sub.add_parser("fix", help="修复 changelog.json 的机械问题")
    fix_p.add_argument("--yes", action="store_true", help="实际写入（默认 dry-run）")

    args = parser.parse_args()

    try:
        if args.cmd == "get":
            if (data := last_round()) is not None:
                for k, v in asdict(data).items():
                    print(f"{LABELS[k]}:{format_value(v)}")
            else:
                print("changelog 为空")
            return

        if args.cmd == "list":
            rounds = list_rounds(args.line)
            if not rounds:
                print("changelog 为空")
                return
            for i, data in enumerate(rounds):
                if i > 0:
                    print("---")
                for k, v in asdict(data).items():
                    print(f"{LABELS[k]}:{format_value(v)}")
            return

        if args.cmd == "fix":
            fix(yes=args.yes)
            return

        record = append(
            author=args.author,
            status=args.status,
            conclusion=args.conclusion,
            scope=args.scope,
            changes=args.changes,
            issues=args.issues,
            mismatches=args.mismatches,
            suggestions=args.suggestions,
            blockers=args.blockers,
            no_fix_reasons=args.no_fix_reasons,
            rejection_judgement=args.rejection_judgement,
            judgement_note=args.judgement_note,
        )
        print(f"成功追加了轮次 {record.round}")

    except InvalidField as e:
        print(f"错误: {e.field} 取值非法 ({e.value!r})")
        print(f"允许的值: {', '.join(map(str, e.allowed))}")
        sys.exit(1)

    except TimeoutError as e:
        print(f"错误: {e}")
        print("提示: 锁被占用或残留，稍后重试或检查 changelog.lock")
        sys.exit(1)

    except CorruptChangelog as e:
        print(f"错误: changelog.json 已损坏: {e}")
        print("提示: 文件被外部修改或损坏，请修复后重试，或恢复备份。")
        sys.exit(1)

    except AlternateError as e:
        print(f"错误: 上一条记录的作者也是 {e.author}，轮转未推进")
        print(f"上一条状态: {e.prev.status}")
        print(f"当前应由: {'功能审查者' if e.author == '功能实现者' else '功能实现者'}")
        sys.exit(1)


if __name__ == "__main__":
    main()