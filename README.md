# dual-agent-review

一个符合 [Agent Skills 规范](https://agentskills.io/specification) 的 Skill：让主 Agent 当审查者、派发的 Sub Agent 当实现者，把「写代码」和「验收代码」拆开。

> 本仓库原名 `dual_agent_collaboration_agreement`，在 2.0 版本重构为 Skill 后更名为 `dual-agent-review`。

## 这是什么

一个 Skill 目录：

```
dual-agent-review/
├── SKILL.md      # 必需：frontmatter + 指令
└── LICENSE
```

- **主 Agent（审查者）**：定标准、派活、独立验证、给结论。不写代码。
- **Sub Agent（实现者）**：只实现，不验收。看不到对话历史。

主 Agent 把需求翻译成一份自包含的任务说明，派给 Sub Agent；Sub Agent 实现完汇报；主 Agent 独立验证并判定。一次同步调用完成交接。

## 为什么不需要偏见防护机制

旧版本用两个独立会话协作，彼此看不见对方，所以需要一份磁盘上的交接日志加一个工具来管轮转、状态和并发写。

现在改成主 Agent 直接派发 Sub Agent：

- Sub Agent **完全没有本次对话的上下文**，它只看到一份任务说明。偏见从何而起？
- 主 Agent 审的是一份**外来交付物**，不是自己刚写的东西。立场天然独立。
- 通信是同一次调用内的请求 / 返回，**没有跨会话可见性问题**，所以交接日志、状态机、锁、原子写入统统是多余的一层。

少一层机制，少一处出错点。

## 安装

本仓库是**源头**，供任何工具安装。把 `dual-agent-review/` 整个目录放进你所用工具的 Skill 目录即可（不同工具路径不同）。

也可以只取 `SKILL.md`：

```
curl -O "https://raw.githubusercontent.com/Azusa-mikan/dual-agent-review/refs/heads/main/dual-agent-review/SKILL.md"
```

然后给 Agent 下达任务，例如：

```
按 dual-agent-review 的约定，实现 XXX 功能
```

## 角色职责速查

| | 主 Agent（审查者） | Sub Agent（实现者） |
|---|---|---|
| 写代码 | 禁止 | 负责 |
| 跑测试 | 负责 | 禁止 |
| 编译 / 类型检查 / lint / 构建 | 可运行（只读） | 可运行（只读） |
| 格式化 / `--fix` / `--write` | 禁止 | 负责 |
| 补测试 | 禁止（交回实现者） | 负责 |
| 验收结论 | 唯一有权给出 | 禁止 |

## 停止条件

- **通过**：交付完成。
- **不通过**：列阻塞项返工。同一阻塞项最多驳回 2 次，第 3 次交用户裁决。
- **需用户裁决**：需求有歧义、双方僵持、或超出授权范围。

## 要求

- 你的工具需要支持派发子 Agent（Agent / Task / Subagent 等机制）。
- 无第三方依赖，无需 Python。

## 许可

MIT
