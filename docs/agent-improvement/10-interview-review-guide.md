# 面试复习路线

## 1. 复习顺序

1. `README.md`
2. `docs/agent-improvement/00-current-status.md`
3. `docs/agent-improvement/02-code-map.md`
4. `docs/agent-improvement/11-phase3.1-source-review.md`（Phase 3.1 源码理解笔记）
5. `src/agent/main.py`
6. `src/agent/core/loop.py`
7. `src/agent/tools/registry.py`
8. `src/agent/permissions/checker.py`
9. `src/agent/tools/file_edit.py`
10. `src/agent/tools/file_write.py`
11. `src/agent/tools/bash.py`
12. `tests/test_main_smoke.py`
13. `tests/test_e2e_agent_workflow.py`
14. `docs/agent-improvement/05-interview-qa.md`
15. `docs/agent-improvement/09-resume-version.md`

## 2. 每个文件应该看什么

### `README.md`

看项目定位、真实能力、当前限制和快速开始。

### `00-current-status.md`

看当前成熟度判断，以及哪些点能写进简历、哪些不能。

### `02-code-map.md`

看默认入口、loop、registry、permissions、CLI 和测试之间的关系。

### `src/agent/main.py`

看默认装配：

- `create_default_registry()`
- `create_agent_loop()`
- `create_agent_app()`
- `main()`

### `src/agent/core/loop.py`

看主循环、工具执行入口、权限处理、workspace guard、tool result 回注。

### `src/agent/tools/registry.py`

看为什么需要统一的工具注册与执行入口。

### `src/agent/permissions/checker.py`

看 `ALLOW / ASK / DENY` 的策略来源。

### `src/agent/tools/file_edit.py`

看 diff preview、唯一匹配约束、原子写入失败保护。

### `src/agent/tools/file_write.py`

看为什么默认不覆盖已有文件。

### `src/agent/tools/bash.py`

看 timeout、输出截断、环境变量白名单和 Windows fallback。

### `tests/test_main_smoke.py`

看默认入口装配如何被测试锁住。

### `tests/test_e2e_agent_workflow.py`

看任务级闭环如何被验证。

### `05-interview-qa.md`

看高频问题的真实答法。

## 3. 面试讲项目的 3 分钟版本

可以这样讲：

> 这个项目是一个参考 Claude Code / Codex 思路实现的本地 Python code agent demo，目标是在本地 workspace 内完成多轮对话、工具调用、代码修改和结果回注。  
>  
> 架构上，我把它拆成了几个清晰层次：`main.py` 负责默认装配，`AgentLoop` 负责多轮调度，`ToolRegistry` 统一管理工具注册、校验和执行，具体工具包括 `bash`、`read`、`write`、`edit`、`grep` 和 `glob`，CLI 层负责渲染和用户确认。  
>  
> 我重点做的不是堆功能，而是把几个关键工程问题补扎实。第一是权限系统，我把高风险工具调用区分成 `ALLOW / ASK / DENY`，其中 `ASK` 必须通过 CLI confirmation handler 得到用户批准，非交互环境下默认 fail-closed。第二是文件编辑安全，`file_edit` 支持 diff preview，并且在 apply 时使用原子写入，避免失败时破坏原文件。第三是 workspace guard，限制文件和搜索类工具不能越出当前工作区。  
>  
> 为了证明这不是只堆了一堆工具，我还补了两类测试：一类是默认入口 smoke test，验证 `main.py` 的默认装配、confirmation handler 和 CLI 命令没有断线；另一类是任务级 e2e regression，用 fake model 驱动真实 loop 和真实 tools，覆盖“读文件、改 bug、跑测试”“权限拒绝/批准”“workspace guard 越界拦截”。  
>  
> 当前我把这个项目定义成 Demo / 展示级，而不是 production-ready，因为它还没有完整 rollback、OS-level sandbox、MCP、WebUI 和更成熟的 session 级权限系统。但作为一个可演示、可复习、可写进简历的 code agent 项目，它已经能比较完整地体现 agent loop、工具系统、安全边界和测试工程化。

## 4. 面试讲项目的 1 分钟版本

> 这是一个本地 Python code agent demo，参考 Claude Code 的思路实现了 `AgentLoop -> ToolRegistry -> tools` 的多轮工具调用闭环。  
> 我重点做了三件事：一是高风险工具的 `ALLOW / ASK / DENY` 权限确认；二是带 diff preview 和原子写入保护的文件编辑；三是入口 smoke test 和任务级 e2e regression，证明它不是只堆工具。  
> 当前它适合定位成可演示、可写进简历的 demo，还不是 production-ready，也没有 MCP、WebUI 和完整 rollback。

## 5. 高频追问

### 你这个项目和 Claude Code 差在哪里？

- 我的是本地 Python demo
- 没有 MCP / WebUI / 完整产品化能力
- 重点是核心 agent loop、工具系统、安全边界和测试

### 你怎么实现 tool calling？

- 模型输出 tool call
- `AgentLoop` 解析
- `ToolRegistry` 负责查找、校验、权限和执行
- 结果再回注到消息历史

### 为什么需要 ToolRegistry？

- 统一管理工具定义和执行协议
- 避免 loop 直接知道每个工具细节

### AgentLoop 怎么避免死循环？

- `max_turns`
- `max_tool_calls`
- repeat detector
- retry limiter

### 权限 ASK 为什么不能默认执行？

- ASK 就是“需要额外确认”
- 默认执行等于没有权限边界

### `file_edit` 为什么要 diff preview？

- 让修改可见
- 便于确认
- 也为后续 rollback 留接口

### workspace guard 怎么做？

- 在 loop 层统一拦截 `read / write / edit / grep / glob`
- 路径越界就拒绝

### e2e 测试证明了什么？

- 证明 agent 能完成任务闭环
- 不是只会单独调用工具

### 为什么现在还不是 production-ready？

- 没有 OS-level sandbox
- 没有完整 rollback
- 真实远程 LLM 回归不完整
- session 级权限策略还不成熟

### 你参考 Nanobot 学了什么，但哪些没做？

- 学的是 code agent 的分层思路和工程化边界意识
- 没有实现它那种完整平台能力，也没有把它当成自己的项目来讲
