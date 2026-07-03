## ADDED Requirements

### Requirement: Plan Mode 激活

系统 SHALL 支持 Plan Mode，用户表达规划意图时 agent 进入规划阶段。

#### Scenario: 用户表达规划意图

- **WHEN** 用户说"先规划"、"先想清楚"、"列出计划"等规划意图
- **THEN** agent 进入 Plan Mode，先输出计划再等待确认

#### Scenario: Plan Mode 标记

- **WHEN** agent 进入 Plan Mode
- **THEN** system prompt 中包含"当前处于计划模式"的标记

### Requirement: Plan Mode 权限控制

系统 SHALL 在 Plan Mode 期间限制可用工具为只读工具。

#### Scenario: 只读工具可用

- **WHEN** 处于 Plan Mode 且调用 read/grep/glob 工具
- **THEN** 工具正常执行

#### Scenario: 写操作被拦截

- **WHEN** 处于 Plan Mode 且调用 write/edit 工具
- **THEN** PermissionChecker 返回 deny，工具不执行

#### Scenario: Bash 写命令被拦截

- **WHEN** 处于 Plan Mode 且 bash 命令包含写操作（rm, mv, echo >, sed -i 等）
- **THEN** PermissionChecker 返回 deny，命令不执行

### Requirement: Plan 输出格式

系统 SHALL 要求 agent 在 Plan Mode 中输出纯文本 markdown 计划。

#### Scenario: 计划包含必要元素

- **WHEN** agent 在 Plan Mode 中输出计划
- **THEN** 计划包含：目标、步骤列表、每步使用的工具

#### Scenario: 计划等待用户确认

- **WHEN** agent 输出计划后
- **THEN** agent 等待用户确认，不自动执行

### Requirement: Plan 确认与修改

系统 SHALL 支持用户确认或修改计划后进入执行模式。

#### Scenario: 用户确认计划

- **WHEN** 用户说"确认"、"执行"、"开始"
- **THEN** agent 退出 Plan Mode，按计划逐步执行

#### Scenario: 用户修改计划

- **WHEN** 用户说"跳过第2步"、"修改第3步"
- **THEN** agent 修改计划，重新输出修改后的版本

#### Scenario: 用户取消计划

- **WHEN** 用户说"取消"、"直接改吧"
- **THEN** agent 退出 Plan Mode，取消计划
