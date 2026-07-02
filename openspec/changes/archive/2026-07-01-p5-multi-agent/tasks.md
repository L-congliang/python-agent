## 1. 基础设施 — Agent 类型系统

- [x] 1.1 创建 `orchestration/__init__.py`
- [x] 1.2 实现 `orchestration/agent_type.py`：AgentTypeDefinition dataclass（name, description, allowed_tools, system_prompt, default_model, default_max_turns）
- [x] 1.3 实现 `orchestration/agent_type.py`：AgentTypeRegistry 类（register, get, get_all）
- [x] 1.4 注册内置类型：general-purpose（所有工具）、explore（read, grep, glob, bash）、code-reviewer（read, grep, glob）
- [x] 1.5 编写 `tests/test_agent_type.py`：类型注册、查找、未知类型回退测试

## 2. 基础设施 — 约束与结果

- [x] 2.1 实现 `orchestration/sub_agent.py`：SubAgentConstraints dataclass（token_budget, tokens_spent, agent_counter, max_agents, abort_controller）
- [x] 2.2 实现 SubAgentConstraints 的方法：remaining_budget(), can_create_agent(), record_agent_created(), record_tokens_spent()
- [x] 2.3 实现 `orchestration/sub_agent.py`：SubAgentResult dataclass（result, status, turns_used, tool_calls_used, tokens_used, agent_type, error）
- [x] 2.4 实现 `orchestration/sub_agent.py`：SubAgentTask dataclass（用于 TaskManager 管理后台任务）
- [x] 2.5 编写 `tests/test_sub_agent.py`：约束检查、预算耗尽、agent 超限测试

## 3. 基础设施 — ToolRegistry 过滤

- [x] 3.1 在 `tools/registry.py` 中新增 filter_by_names(names: list[str]) -> ToolRegistry 方法
- [x] 3.2 在 `tools/registry.py` 中新增 clone() -> ToolRegistry 方法（深拷贝）
- [x] 3.3 编写 `tests/test_registry_filter.py`：过滤、空列表、不存在的名称测试

## 4. 核心实现 — AgentLoop 子 Agent 支持

- [x] 4.1 在 `core/loop.py` 中新增 create_sub_agent() 工厂方法：接收 parent、task、agent_type_def、constraints、extra_context
- [x] 4.2 实现 _build_subagent_prompt() 静态方法：组合 agent_type 的 system_prompt + 父 Agent 的 memory.render_compact() + 工具列表
- [x] 4.3 实现 _filter_registry() 静态方法：从父 Agent 的 registry 过滤出 allowed_tools
- [x] 4.4 修改 AgentLoop.__init__()：新增 _subagent_constraints: SubAgentConstraints | None 属性
- [x] 4.5 修改 AgentLoop.run()：在循环开始前检查子 Agent 约束（token budget、agent counter）
- [x] 4.6 修改 _execute_tool_calls()：子 Agent 模式下累加 tokens_spent 到 SubAgentConstraints
- [x] 4.7 编写 `tests/test_loop_subagent.py`：create_sub_agent、约束检查、记忆注入测试

## 5. 核心实现 — SubAgentTool

- [x] 5.1 创建 `tools/subagent.py`：SubAgentTool 类，实现 Tool Protocol
- [x] 5.2 定义 parameters schema：prompt(required), description(required), agent_type(optional), model(optional), isolation(optional), run_in_background(optional)
- [x] 5.3 实现 execute() 阻塞模式：创建子 Agent、执行、返回 SubAgentResult
- [x] 5.4 实现 execute() 后台模式：创建子 Agent、启动线程、注册到 TaskManager、返回 task_id
- [x] 5.5 实现 validate_input()：检查 prompt 非空、description 非空、agent_type 有效
- [x] 5.6 实现 check_permissions()：子 Agent 的权限检查（默认 allow，交给通用权限系统）
- [x] 5.7 实现 get_summary() 和 get_activity_description()：UI 显示
- [x] 5.8 编写 `tests/test_subagent_tool.py`：阻塞模式、参数校验、结果格式测试

## 6. 核心实现 — TaskManager

- [x] 6.1 创建 `orchestration/message_bus.py`：TaskManager 类
- [x] 6.2 实现 register(task: SubAgentTask) -> str：注册后台任务，返回 task_id
- [x] 6.3 实现 get_status(task_id: str) -> str：查询任务状态
- [x] 6.4 实现 get_result(task_id: str) -> SubAgentResult：阻塞等待结果
- [x] 6.5 实现 stop(task_id: str) -> None：停止后台任务
- [x] 6.6 实现 list_tasks() -> list[dict]：列出所有任务
- [x] 6.7 编写 `tests/test_task_manager.py`：注册、查询、停止、并发测试

## 7. 核心实现 — worktree 隔离

- [x] 7.1 在 SubAgentTool.execute() 中实现 worktree 创建逻辑：git worktree add .worktrees/<task_id>
- [x] 7.2 实现 worktree 清理逻辑：子 Agent 执行完后 git worktree remove
- [x] 7.3 实现 worktree 创建失败回退：失败时回退到非隔离模式
- [x] 7.4 实现孤立 worktree 清理：启动时检查 .worktrees/ 目录，清理未使用的 worktree
- [x] 7.5 编写 `tests/test_worktree.py`：创建、清理、回退测试（mock subprocess）

## 8. 集成 — 注册 SubAgentTool

- [x] 8.1 在 AgentLoop.__init__() 中注册 SubAgentTool 到 ToolRegistry（如果配置允许）
- [x] 8.2 在 LoopConfig 中新增 enable_subagent: bool = True 配置项
- [x] 8.3 在 _build_system_prompt() 中添加 SubAgent 使用说明（何时使用、参数说明）

## 9. 评测

- [x] 9.1 创建 `tests/evaluation/test_multi_agent_benchmark.py`
- [x] 9.2 定义多 Agent 评测任务：主 Agent 派生子 Agent 搜索 TODO
- [x] 9.3 定义多 Agent 评测任务：主 Agent 派生多个子 Agent 并行执行
- [x] 9.4 定义多 Agent 评测任务：子 Agent 嵌套派生子子 Agent
- [x] 9.5 运行评测，记录基线指标

## 10. 文档与清理

- [x] 10.1 更新 `feature_list.json`：标记 P5 为 done
- [x] 10.2 更新 `claude-progress.md`：记录 P5 完成
- [x] 10.3 更新 `DEV_SYNC.md`：记录本次工作内容
- [x] 10.4 运行 `uv run make check` 确保所有验证通过
