# 简历与面试准备材料

更新时间：2026-07-06

## 1. 中文简历 bullet

### 推荐版本（3-4 条）

```
• 设计并实现本地 Python Code Agent，参考 Claude Code 的 AgentLoop -> ToolRegistry -> tools 多轮工具调用闭环，支持 bash/read/write/edit/grep/glob 等基础工具。
• 设计 preview + artifact 双层 Observation 机制，统一长输出截断与落盘，解决 tool-using agent 的上下文膨胀问题。
• 实现 backup / rollback / edit history 与 session-scoped permission policy，支持高风险操作确认、文件修改可回退、相同命令或文件的 session 级复用授权。
• 实现 session/workspace lifecycle management，支持 autosave、--resume latest/<session_id>、/inspect 状态检查与 freshness-aware resume；测试基线 1061 passed, 6 skipped。
```

### 精简版本（3 条，适合简历空间紧张）

```
• 实现本地 Python Code Agent，基于 AgentLoop + ToolRegistry 完成多轮工具调用闭环，支持 bash/read/write/edit/grep/glob。
• 设计 preview + artifact Observation 机制与 backup/rollback/edit history，分别解决上下文膨胀和文件修改可恢复问题。
• 实现 session 持久化、自动保存、resume 与 freshness 检测，测试基线 1061 passed, 6 skipped。
```

## 2. 英文简历 bullet

### Recommended Version (3-4 bullets)

```
• Designed and implemented a local Python Code Agent following Claude Code's AgentLoop -> ToolRegistry -> tools multi-turn tool-calling pattern, supporting bash/read/write/edit/grep/glob.
• Designed preview + artifact dual-layer Observation mechanism, unifying long-output truncation and artifact persistence to solve context explosion in tool-using agents.
• Implemented backup / rollback / edit history and session-scoped permission policy, supporting high-risk operation confirmation, file modification rollback, and session-level authorization reuse.
• Implemented session/workspace lifecycle management with autosave, --resume latest/<session_id>, /inspect status inspection, and freshness-aware resume; test baseline 1061 passed, 6 skipped.
```

### Compact Version (3 bullets)

```
• Implemented local Python Code Agent with AgentLoop + ToolRegistry multi-turn tool-calling pattern, supporting bash/read/write/edit/grep/glob.
• Designed preview + artifact Observation mechanism and backup/rollback/edit history, solving context explosion and file modification recoverability.
• Implemented session persistence, autosave, resume, and freshness detection; test baseline 1061 passed, 6 skipped.
```

## 3. 一分钟讲稿

> 这是一个本地 Python code agent，参考 Claude Code 思路实现了 AgentLoop -> ToolRegistry -> tools 的多轮工具调用闭环。
>
> 我重点解决了 4 类工程问题：上下文膨胀（preview + artifact 双层契约）、文件可回退（backup/rollback/edit history）、权限体验（session-scoped permission policy）、真实远程链路（real remote smoke）。
>
> 最近做了 session/workspace lifecycle management，session 可持久化、可恢复、可检查状态，resume 时能判断 freshness。
>
> 测试基线 1061 passed, 6 skipped，当前定位是偏扎实的 Demo / 展示级，接近 Prototype 边缘。

## 4. 三分钟讲稿

> 这个项目是一个参考 Claude Code 思路实现的本地 Python code agent，目标是解决真实 agent 开发中的工程问题。
>
> **架构上**，我把它拆成几个清晰层次：`main.py` 负责默认装配，`AgentLoop` 负责多轮调度，`ToolRegistry` 统一管理工具注册、校验和执行，具体工具包括 bash、read、write、edit、grep 和 glob，CLI 层负责渲染和用户确认。
>
> **我重点做了 4 类工程问题：**
>
> **第一是上下文膨胀**。长 grep/bash 输出会撑爆上下文。我设计了 Observation Budget 契约，工具输出分成 preview（模型可见）和 artifact（用户可追溯），统一 5 个工具的截断逻辑，长输出自动落盘。
>
> **第二是文件修改可恢复**。write/edit 前自动备份，支持 /history 和 /rollback latest，新建文件 rollback 会删除，修改文件 rollback 会恢复原内容。
>
> **第三是权限体验**。高风险工具调用区分 ALLOW / ASK / DENY，ASK 必须通过 CLI 确认。我实现了 Session 级 Permission Policy，相同命令/文件可以 session 复用批准，减少重复 ASK。
>
> **第四是真实远程链路**。不只是 fake-model e2e，还有真实远程 LLM smoke，环境门控 + 收敛 prompt，验证真实 API 链路没断。
>
> **最近一轮我做了 session/workspace lifecycle management**。session 可持久化、可恢复，--resume latest 能接回上次对话，/inspect 能看到当前 run/session/workspace/checkpoint/freshness 状态。resume 时能判断 freshness，不是盲目接着跑。
>
> **测试基线**是 1061 passed, 6 skipped，包含单元测试、集成测试、fake-model e2e、真实远程 smoke。
>
> **当前定位**是偏扎实的 Demo / 展示级，接近 Prototype 边缘。还没有 MCP、WebUI、完整 rollback、production-ready sandbox，但作为一个可演示、可复习、可写进简历的 code agent 项目，它已经能比较完整地体现 agent loop、工具系统、安全边界和测试工程化。

## 5. 高频追问标准回答

### Q：你这个项目和 Claude Code 差在哪里？

**A：**
- 我的是本地 Python demo，没有 MCP / WebUI / 完整产品化能力
- 重点是核心 agent loop、工具系统、安全边界和测试
- 但我在 observation/artifact、session lifecycle、freshness 检测上做了工程化

### Q：你怎么解决上下文膨胀？

**A：**
- 设计 Observation Budget 契约
- 工具输出分成 preview（模型可见）和 artifact（用户可追溯）
- 统一 5 个工具的截断逻辑（bash 保留尾部，read/grep/glob 保留头部）
- 长输出自动落盘，路径记录在 metadata 中

### Q：你怎么实现 session 持久化？

**A：**
- SessionStore 二层结构：raw resumable state（供程序恢复）+ summary/preview（供展示）
- --resume latest / --resume \<session_id\> 恢复 session
- autosave 进入默认使用体验，/reset 后新旧 session 分离
- resume 时检测 freshness，四类状态清晰可见

### Q：为什么 freshness 只做检测和提示，不做自动恢复？

**A：**
- 自动恢复会引入复杂逻辑（哪些文件恢复？怎么恢复？）
- 自动恢复可能覆盖用户手动修改
- 只做检测和提示，让用户决定
- 这是"保守但安全"的设计

### Q：为什么 session 要分 raw state 和 summary？

**A：**
- raw state 用于真正恢复，需要完整数据（messages、memory、workspace_root、last_run_id）
- summary 用于展示，只需要摘要（id、created_at、message_count）
- 如果只保存 summary，无法恢复
- 如果只保存 raw state，展示时会泄露敏感信息

### Q：你的测试策略是什么？

**A：**
- 单元测试：测试单个函数/类
- 集成测试：测试多个模块协作
- Fake-model e2e：使用 FakeModelClient 的端到端测试
- 真实远程 smoke：验证真实 API 链路没断（需 RUN_REAL_LLM_SMOKE=1 + MIMO_API_KEY）
- 测试基线 1061 passed, 6 skipped

### Q：为什么现在还不是 production-ready？

**A：**
- 没有 OS-level sandbox
- 没有完整 rollback（只支持 latest）
- 真实远程 LLM 回归不完整（只有 smoke，没有完整 e2e）
- session 级权限策略还不成熟（只支持 bash/write/edit）
- 还没有 MCP、WebUI、复杂多 agent 并行

### Q：你参考 Nanobot / Hermes 学了什么？

**A：**
- 从 Nanobot 学的是：workspace/session 管理、tool registry / adapter 抽象、safety / workspace restriction
- 从 Hermes 学的是：trajectory / observation compression
- 没有实现的是：MCP、WebUI、复杂多 agent 并行、长期 memory 产品化、Hermes 式 self-improving loop

## 6. 最该避免的说法

- ❌ 不要说"我做了 Claude Code"
- ❌ 不要说"生产级"
- ❌ 不要说"完整 rollback"
- ❌ 不要说"真实完整 e2e benchmark 已完备"
- ❌ 不要把 real remote smoke 说成大规模线上评测

## 7. 推荐演示路径

1. 跑 `tests/test_e2e_agent_workflow.py`，证明 agent 能完成任务闭环
2. 解释它证明了什么：读文件、改 bug、跑测试、权限拒绝/批准、workspace guard 越界拦截
3. 说明这一步不需要 API key，使用的是 fake-model e2e
4. 配好 API key 后启动 CLI
5. 演示一次 `edit` 的 diff preview + 用户确认
6. 再展示 workspace guard 和默认拒绝覆盖
7. 演示 `/session`、`/sessions`、`/inspect` 命令
8. 演示 `--resume latest` 恢复 session
