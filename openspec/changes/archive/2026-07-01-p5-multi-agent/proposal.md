## Why

当前 Agent 只有单循环模式，所有任务都由主 Agent 串行执行。面对需要并行探索、独立上下文、或后台执行的场景（如"搜索所有 TODO 并同时检查类型注解"），单 Agent 无法高效处理。对齐 Claude Code 的 AgentTool，实现多 Agent 编排能力，是面试 6 个核心知识点中"多 Agent 路由"的直接对应。

## What Changes

- 新增 SubAgentTool，作为普通工具注册到 ToolRegistry，主 Agent 通过调用此工具派生子任务
- 新增 Agent 类型系统（AgentTypeRegistry），支持 general-purpose / explore / code-reviewer 等内置类型
- 子 Agent 复用 AgentLoop 实例，通过配置关闭不需要的功能（记忆、checkpoint、trace）
- 子 Agent 继承父 Agent 的记忆（通过 system prompt 注入），但不共享 MemoryManager 实例
- 支持嵌套子 Agent，通过 SubAgentConstraints 跨层级共享 token budget、abort signal、agent counter
- 支持后台执行模式（run_in_background），通过 TaskManager 管理异步任务
- 支持 worktree 隔离模式，子 Agent 在独立 git worktree 中执行
- 修改 AgentLoop，新增 create_sub_agent() 工厂方法
- 修改 ToolRegistry，新增 filter_by_names() 方法支持工具集过滤

## Capabilities

### New Capabilities

- `multi-agent`: 多 Agent 编排系统 — SubAgentTool、Agent 类型注册、子 Agent 上下文隔离、嵌套支持、后台执行、worktree 隔离、约束传递

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- **新增模块**: `orchestration/`（agent_type.py, sub_agent.py, message_bus.py）
- **新增工具**: `tools/subagent.py`
- **修改文件**: `core/loop.py`（新增工厂方法和约束检查）、`tools/registry.py`（新增过滤方法）
- **新增测试**: test_subagent.py, test_agent_type.py, test_task_manager.py
- **依赖**: 无新增外部依赖（git worktree 用 subprocess 调用）
- **运行时目录**: `.worktrees/`（worktree 隔离模式使用）
