## ADDED Requirements

### Requirement: System Prompt 优化

系统 SHALL 提供结构化的系统提示词，包含：agent 身份、可用工具列表、工具使用指南、SubAgent 使用说明、输出格式要求。

#### Scenario: 完整系统提示词

- **WHEN** 构建 prompt
- **THEN** system prompt 包含 agent 身份、工具列表、使用指南、SubAgent 使用说明

#### Scenario: SubAgent 使用指南

- **WHEN** 模型阅读 system prompt
- **THEN** 模型知道何时使用 subagent 工具（搜索大量文件、复杂多步任务、需要独立上下文的任务）

### Requirement: Tool Description 优化

系统 SHALL 为每个工具提供精准的 description，让模型能正确选择工具。Description 包含：用途、适用场景、参数说明、示例。

#### Scenario: 模型正确选择工具

- **WHEN** 用户说 "读取 main.py"
- **THEN** 模型选择 read_file 工具

#### Scenario: 模型区分相似工具

- **WHEN** 用户说 "修改 main.py 的第 10 行"
- **THEN** 模型选择 edit_file 工具（不是 write_file）

### Requirement: Plan Mode

系统 SHALL 支持 Plan Mode：多步任务先列出计划，用户确认后再执行。Plan 包含：目标、步骤列表、每步使用的工具、预期结果。

#### Scenario: 启用 Plan Mode

- **WHEN** 用户说 "先规划再执行"
- **THEN** agent 先输出计划，等待用户确认

#### Scenario: 计划确认后执行

- **WHEN** 用户确认计划
- **THEN** 按计划逐步执行

#### Scenario: 计划修改

- **WHEN** 用户说 "跳过第 2 步"
- **THEN** 修改计划，跳过第 2 步后继续执行
