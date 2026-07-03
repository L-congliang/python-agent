## ADDED Requirements

### Requirement: SubAgentTool

系统 SHALL 提供 SubAgentTool，作为普通工具注册到 ToolRegistry。主 Agent 通过调用此工具派生子任务。

#### Scenario: 主 Agent 派生子 Agent

- **WHEN** 主 Agent 调用 subagent 工具，参数为 `{"task": "搜索所有 TODO", "tools": ["grep", "glob"]}`
- **THEN** 系统创建子 Agent，子 Agent 只接收 task 描述，不接收主 Agent 的完整历史

#### Scenario: 子 Agent 执行并返回结果

- **WHEN** 子 Agent 执行完成
- **THEN** 子 Agent 返回结果给主 Agent，子 Agent 的上下文销毁

#### Scenario: 主 Agent 指定子 Agent 的工具集

- **WHEN** 主 Agent 调用 subagent 工具，指定 `tools` 参数
- **THEN** 子 Agent 只能使用指定的工具，不能使用未指定的工具

### Requirement: 子 Agent 上下文隔离

系统 SHALL 确保子 Agent 有独立的上下文，不污染主 Agent 的上下文。

#### Scenario: 子 Agent 不接收主 Agent 的完整历史

- **WHEN** 主 Agent 派生子 Agent
- **THEN** 子 Agent 只接收 task 描述，不接收主 Agent 的消息历史

#### Scenario: 子 Agent 有独立的 MemoryManager

- **WHEN** 子 Agent 创建
- **THEN** 子 Agent 有独立的 MemoryManager，不与主 Agent 共享

#### Scenario: 子 Agent 执行完销毁

- **WHEN** 子 Agent 执行完成
- **THEN** 子 Agent 的上下文（包括 MemoryManager）销毁，不污染主 Agent

### Requirement: task_summary 传递

系统 SHALL 支持从主 Agent 上下文中提取必要信息传递给子 Agent。

#### Scenario: 传递 task_summary

- **WHEN** 主 Agent 派生子 Agent，且需要传递上下文
- **THEN** 系统从主 Agent 的最近消息中提取 task_summary，传递给子 Agent

#### Scenario: task_summary 包含必要信息

- **WHEN** 提取 task_summary
- **THEN** task_summary 包含最近 5 条消息的摘要，不包含完整历史
