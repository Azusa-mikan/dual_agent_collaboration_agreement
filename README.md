# 双 Agent 协作约定

让两个 AI Agent 协作完成一个任务：一个实现，一个审查，互相不越界。

## 这是什么

一份约定（`AGENTS.md`）加一个工具（`daca.py`），用来让两个 Agent 分角色干活：

- **功能实现者**：只写代码，不审自己的代码，不跑测试。
- **功能审查者**：只审代码，不写代码，跑测试。

两者通过 `changelog.json` 交接，谁该上场由最新一条记录的状态决定。所有读写都经过 `daca.py`，它强制轮次连续、状态合法、写入原子。

## 为什么需要

让同一个 Agent 既写又审，它倾向于认为自己对。拆成两个角色、两个会话，审查者拿到的是一份已经完成的东西，立场天然不同。

约定是软的——Agent 理解它，但不保证每次都照做。`daca.py` 是硬的——它不让非法状态写进去。两层配合，才跑得稳。

## 怎么用

1. 在项目根目录运行

```
curl -O "https://raw.githubusercontent.com/Azusa-mikan/dual_agent_collaboration_agreement/refs/heads/main/AGENTS.md"

# daca.py 会在 Agent 首次运行时按 AGENTS.md 4.0 节自动下载，
# 也可以手动获取：
curl -O "https://raw.githubusercontent.com/Azusa-mikan/dual_agent_collaboration_agreement/refs/heads/main/daca.py"
```


2. 给两个 Agent 分别指定角色，例如：
   - 会话 A：“你是功能实现者，实现 XXX”
   - 会话 B：“你是功能审查者，看看实现者做得怎么样”

不同会话可以来自不同工具，不必是同一软件的不同对话。

3. 剩下的按 `AGENTS.md` 走。

## 命令

| 命令 | 用途 |
|---|---|
| `python daca.py get` | 看最后一条记录 |
| `python daca.py list [--line N]` | 看最近 N 条，默认 10 |
| `python daca.py add ...` | 追加一条记录 |
| `python daca.py fix [--yes]` | 修复 `changelog.json` 的机械问题，默认 dry-run |

`add` 的完整参数和用法见 `AGENTS.md` 第 4 节。

必须先有 daca.py 才能使用

## 状态

`changelog.json` 中每条记录有一个状态：

- `待审查`：等审查者
- `待实现`：等实现者
- `已通过`：结束
- `需用户裁决`：停，等人

## 要求

- Python 3.10+
- 无第三方依赖

## 许可

MIT