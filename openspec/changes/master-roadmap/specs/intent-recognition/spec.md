## ADDED Requirements

### Requirement: System Prompt 优化

系统 SHALL 提供结构化的系统提示词，包含：agent 身份、可用工具列表、工具使用指南、输出格式要求、安全规则。

#### Scenario: 完整系统提示词

- **WHEN** 构建 prompt
- **THEN** system prompt 包含 agent 身份、工具列表、使用指南

#### Scenario: 工具描述准确

- **WHEN** 模型阅读工具描述
- **THEN** 能正确理解每个工具的用途和参数

### Requirement: Tool Description 优化

系统 SHALL 为每个工具提供精准的 description，让模型能正确选择工具。Description 包含：用途、适用场景、参数说明、示例。

#### Scenario: 模型正确选择工具

- **WHEN** 用户说 "读取 main.py"
- **THEN** 模型选择 read_file 工具

#### Scenario: 模型区分相似工具

- **WHEN** 用户说 "修改 main.py 的第 10 行"
- **THEN** 模型选择 edit_file 工具（不是 write_file）

### Requirement: 意图分类

系统 SHALL 支持将用户输入分类为：code-edit（代码编辑）、code-search（代码搜索）、question（问答）、chat（闲聊）。

#### Scenario: 分类代码编辑

- **WHEN** 用户输入 "修复 bug 在 line 42"
- **THEN** 分类为 code-edit

#### Scenario: 分类代码搜索

- **WHEN** 用户输入 "找到所有使用 foo 函数的地方"
- **THEN** 分类为 code-search

#### Scenario: 分类问答

- **WHEN** 用户输入 "这个项目是做什么的"
- **THEN** 分类为 question

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
