# 简历版本

## 1. 项目一句话介绍

这是一个参考 Claude Code / Codex 思路实现的本地 Python code agent demo，支持多轮工具调用、权限确认、diff-based 文件编辑和任务级 e2e regression。

## 2. 简历 bullet 中文版

- 设计并实现本地 Python code agent，基于 `AgentLoop -> ToolRegistry -> tools` 完成多轮 tool-calling 闭环，支持文件读取、写入、编辑、搜索与 shell 执行。
- 实现统一工具系统与权限策略，区分 `ALLOW / ASK / DENY` 三类权限决策，并通过 CLI confirmation handler 对高风险 `bash / write / edit` 操作进行显式确认。
- 实现 diff-based 文件编辑流程，支持 unified diff preview、模糊匹配拒绝和原子写入失败保护，提升代码修改的可见性与安全性。
- 为 shell 工具补充超时、输出截断、环境变量白名单和 Windows fallback，增强跨平台可用性与运行时安全边界。
- 实现 workspace guard，限制 `read / write / edit / grep / glob` 仅在当前工作区内访问，避免路径逃逸和越界搜索。
- 编写入口 smoke test 与任务级 e2e regression，覆盖默认装配、权限确认、代码修复与测试执行闭环，支撑项目演示、复习和面试表达。

## 3. 简历 bullet 英文版

- Built a local Python code agent around an `AgentLoop -> ToolRegistry -> tools` workflow, enabling multi-turn tool calling for file read/write/edit, search, and shell execution.
- Implemented a permission layer with `ALLOW / ASK / DENY` semantics and a CLI confirmation handler for high-risk `bash`, `write`, and `edit` operations.
- Developed a diff-based file editing flow with unified diff preview, ambiguous-match rejection, and atomic-write failure protection to improve edit safety and auditability.
- Added timeout, output truncation, environment allowlisting, and Windows shell fallback for the bash tool to improve cross-platform reliability and safety boundaries.
- Enforced workspace-scoped access for `read`, `write`, `edit`, `grep`, and `glob` to prevent path escape and out-of-workspace search.
- Wrote smoke tests and task-level e2e regressions covering default runtime wiring, permission confirmation, bug-fixing workflow, and test execution.

## 4. 面试中不能说的点

- 不能说这是 production-ready 项目
- 不能说完整复刻了 Claude Code
- 不能说 Nanobot 是自己做的
- 不能说 MCP 已实现
- 不能说已经支持真实多 agent 并行
- 不能说 `file_edit` 已有完整 rollback
- 不能说 e2e 是真实远程 LLM e2e

## 5. 面试时推荐说法

推荐说法：

> 这是一个参考 Claude Code / Nanobot 思路实现的本地 Python code agent demo。  
> 我重点做的是 agent loop、工具系统、权限确认、文件编辑安全和 e2e regression，而不是完整复刻 Claude Code 或直接做成生产级产品。
