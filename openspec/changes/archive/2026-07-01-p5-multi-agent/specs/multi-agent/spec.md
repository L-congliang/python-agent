## ADDED Requirements

### Requirement: SubAgentTool 注册

系统 SHALL 提供 SubAgentTool，作为普通工具注册到 ToolRegistry。SubAgentTool 的 name 为 "subagent"，参数包含 prompt（required）、description（required）、agent_type（optional）、model（optional）、isolation（optional）、run_in_background（optional）。

#### Scenario: SubAgentTool 已注册

- **WHEN** AgentLoop 初始化
- **THEN** SubAgentTool 已注册到 ToolRegistry，模型可以通过 tool_use 调用

#### Scenario: 模型调用 SubAgentTool

- **WHEN** 模型返回 tool_use block，name="subagent"，arguments={"prompt": "搜索所有TODO", "description": "搜索TODO注释"}
- **THEN** 系统创建子 Agent 并执行，返回结果

### Requirement: 子 Agent 创建

系统 SHALL 通过 AgentLoop.create_sub_agent() 工厂方法创建子 Agent。子 Agent 复用 AgentLoop 实例，通过 LoopConfig 关闭不需要的功能。

#### Scenario: 创建子 Agent

- **WHEN** SubAgentTool.execute() 被调用
- **THEN** 系统调用 AgentLoop.create_sub_agent()，传入父 Agent、task、agent_type 定义、约束
- **AND** 子 Agent 的 LoopConfig 中 enable_trace=False, enable_checkpoint=False

#### Scenario: 子 Agent 使用父 Agent 的客户端

- **WHEN** 子 Agent 创建
- **THEN** 子 Agent 使用父 Agent 的同一个 MimoClient 和 ModelAdapter

### Requirement: 子 Agent 上下文隔离

系统 SHALL 确保子 Agent 有独立的上下文，不污染主 Agent 的上下文。子 Agent 有独立的消息历史和 MemoryManager。

#### Scenario: 子 Agent 有独立消息历史

- **WHEN** 子 Agent 创建
- **THEN** 子 Agent 的消息历史为空，只包含 system prompt 和用户输入（task 描述）

#### Scenario: 子 Agent 有独立 MemoryManager

- **WHEN** 子 Agent 创建
- **THEN** 子 Agent 有独立的 MemoryManager 实例，不与父 Agent 共享
- **AND** 子 Agent 的 MemoryManager 不 load 持久记忆

#### Scenario: 子 Agent 执行完销毁

- **WHEN** 子 Agent 执行完成
- **THEN** 子 Agent 的上下文（消息历史、MemoryManager）销毁，不污染父 Agent

### Requirement: 父 Agent 记忆注入

系统 SHALL 将父 Agent 的记忆通过 system prompt 注入子 Agent，使子 Agent 知道父 Agent 之前的操作上下文。

#### Scenario: 注入父 Agent 记忆

- **WHEN** 子 Agent 创建
- **THEN** 子 Agent 的 system prompt 包含父 Agent 的 memory.render_compact() 输出

#### Scenario: 注入是只读的

- **WHEN** 子 Agent 执行过程中修改自己的 MemoryManager
- **THEN** 父 Agent 的 MemoryManager 不受影响

### Requirement: Agent 类型系统

系统 SHALL 提供 AgentTypeRegistry，支持注册和查找 Agent 类型定义。每个类型定义包含 name、description、allowed_tools、system_prompt、default_model、default_max_turns。

#### Scenario: 内置类型注册

- **WHEN** AgentTypeRegistry 初始化
- **THEN** 内置类型已注册：general-purpose、explore、code-reviewer

#### Scenario: 按类型过滤工具集

- **WHEN** 子 Agent 使用 agent_type="explore" 创建
- **THEN** 子 Agent 的 ToolRegistry 只包含 explore 类型定义的 allowed_tools

#### Scenario: 未知类型回退到 general-purpose

- **WHEN** 子 Agent 使用不存在的 agent_type 创建
- **THEN** 系统回退到 general-purpose 类型

### Requirement: 工具集过滤

系统 SHALL 支持通过 ToolRegistry.filter_by_names() 方法创建受限的工具注册表。

#### Scenario: 过滤工具

- **WHEN** 调用 registry.filter_by_names(["read", "grep", "glob"])
- **THEN** 返回新的 ToolRegistry，只包含指定名称的工具

#### Scenario: 空列表返回空注册表

- **WHEN** 调用 registry.filter_by_names([])
- **THEN** 返回空的 ToolRegistry

### Requirement: 嵌套子 Agent

系统 SHALL 支持嵌套子 Agent（子 Agent 再派生子 Agent）。嵌套时通过 SubAgentConstraints 共享约束，防止无限递归。

#### Scenario: 子 Agent 可以派生子 Agent

- **WHEN** 子 Agent 调用 subagent 工具
- **THEN** 系统创建子子 Agent，共享父 Agent 的 SubAgentConstraints

#### Scenario: 共享 token budget

- **WHEN** 嵌套子 Agent 执行
- **THEN** 所有层级的 Agent 共享同一个 token_budget
- **AND** tokens_spent 跨层级累加

#### Scenario: 共享 abort signal

- **WHEN** 父 Agent 调用 abort()
- **THEN** 所有子 Agent（包括嵌套的）都收到 abort 信号

#### Scenario: agent counter 上限

- **WHEN** 已创建的 agent 数量达到 max_agents（默认 100）
- **THEN** 新的 subagent 调用返回错误

### Requirement: 子 Agent 轮次限制

系统 SHALL 为子 Agent 设置独立的轮次限制，子 Agent 的 max_turns 不能超过父 Agent 的剩余轮次。

#### Scenario: 子 Agent 使用类型默认轮次

- **WHEN** 子 Agent 使用 agent_type="explore" 创建，explore 类型的 default_max_turns=20
- **THEN** 子 Agent 的 max_turns 为 20

#### Scenario: 子 Agent 轮次不能超过父 Agent 剩余轮次

- **WHEN** 父 Agent 剩余轮次为 10，子 Agent 的 default_max_turns 为 20
- **THEN** 子 Agent 的 max_turns 被限制为 10

### Requirement: 子 Agent 工具权限

系统 SHALL 对子 Agent 的工具执行权限检查。子 Agent 的工具执行经过与主 Agent 相同的权限流程。

#### Scenario: 子 Agent 执行工具需要权限检查

- **WHEN** 子 Agent 调用 bash 工具
- **THEN** 经过与主 Agent 相同的权限检查流程

#### Scenario: 子 Agent 只能使用类型允许的工具

- **WHEN** 子 Agent 的 agent_type 的 allowed_tools 不包含 "bash"
- **THEN** 子 Agent 的 ToolRegistry 中没有 bash 工具，无法调用

### Requirement: 子 Agent 结果格式

系统 SHALL 返回结构化的 SubAgentResult，包含 result（最终回复文本）、status（完成状态）、turns_used（轮次）、tool_calls_used（工具调用次数）、tokens_used（token 消耗）、agent_type（类型）。

#### Scenario: 子 Agent 正常完成

- **WHEN** 子 Agent 执行完成，没有错误
- **THEN** 返回 SubAgentResult，status="completed"，result 包含最终回复文本

#### Scenario: 子 Agent 被中断

- **WHEN** 子 Agent 执行被 abort
- **THEN** 返回 SubAgentResult，status="stopped"，error 包含中断原因

#### Scenario: 子 Agent 超过轮次限制

- **WHEN** 子 Agent 超过 max_turns
- **THEN** 返回 SubAgentResult，status="stopped"，error="超过最大轮次限制"

#### Scenario: 子 Agent 模型调用失败

- **WHEN** 子 Agent 的模型调用抛出异常
- **THEN** 返回 SubAgentResult，status="failed"，error 包含异常信息

### Requirement: 后台执行模式

系统 SHALL 支持子 Agent 后台执行模式。当 run_in_background=True 时，SubAgentTool 立即返回 task_id，子 Agent 在独立线程中执行。

#### Scenario: 启动后台子 Agent

- **WHEN** 调用 subagent(prompt="...", run_in_background=true)
- **THEN** SubAgentTool 立即返回 {"task_id": "sa_xxxxx", "status": "running"}

#### Scenario: 查询后台任务状态

- **WHEN** 调用 TaskManager.get_status(task_id)
- **THEN** 返回任务当前状态："running" | "completed" | "stopped" | "failed"

#### Scenario: 获取后台任务结果

- **WHEN** 调用 TaskManager.get_result(task_id)
- **THEN** 阻塞等待任务完成，返回 SubAgentResult

#### Scenario: 停止后台任务

- **WHEN** 调用 TaskManager.stop(task_id)
- **THEN** 后台任务的 AbortController 触发 abort，任务停止

### Requirement: worktree 隔离模式

系统 SHALL 支持子 Agent 的 worktree 隔离模式。当 isolation="worktree" 时，系统创建 git worktree，子 Agent 在独立目录中执行。

#### Scenario: 创建 worktree

- **WHEN** 调用 subagent(prompt="...", isolation="worktree")
- **THEN** 系统执行 git worktree add，在 .worktrees/ 目录创建独立工作目录

#### Scenario: 子 Agent 在 worktree 中执行

- **WHEN** 子 Agent 使用 worktree 隔离模式
- **THEN** 子 Agent 的 workspace_root 指向 worktree 目录
- **AND** 子 Agent 的文件操作（read/write/edit）在 worktree 目录中进行

#### Scenario: 清理 worktree

- **WHEN** 子 Agent 执行完成
- **THEN** 系统执行 git worktree remove，清理 worktree 目录

#### Scenario: worktree 创建失败回退

- **WHEN** git worktree add 失败（如 git 版本不支持）
- **THEN** 系统回退到非隔离模式，子 Agent 在主 Agent 的工作目录中执行

### Requirement: SubAgentConstraints 约束传递

系统 SHALL 通过 SubAgentConstraints 在父子 Agent 之间传递约束。约束包含 token_budget、tokens_spent、agent_counter、max_agents、abort_controller。

#### Scenario: 约束创建

- **WHEN** 主 Agent 首次调用 subagent
- **THEN** 系统创建 SubAgentConstraints，从 LoopConfig 读取 token_budget

#### Scenario: 约束传递给子 Agent

- **WHEN** 子 Agent 创建
- **THEN** 子 Agent 持有父 Agent 的 SubAgentConstraints 引用

#### Scenario: 约束检查 — token 预算耗尽

- **WHEN** SubAgentConstraints.remaining_budget() <= 0
- **THEN** 新的 subagent 调用返回错误 "Token 预算已耗尽"

#### Scenario: 约束检查 — agent 数量超限

- **WHEN** SubAgentConstraints.agent_counter >= max_agents
- **THEN** 新的 subagent 调用返回错误 "超过最大 Agent 数量限制"
