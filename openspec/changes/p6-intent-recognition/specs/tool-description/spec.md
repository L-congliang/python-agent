## MODIFIED Requirements

### Requirement: Tool Description 微调

系统 SHALL 在关键工具的 description 中加入选择提示，引导模型优先使用更合适的工具。

#### Scenario: edit 工具描述包含优先级提示

- **WHEN** 模型阅读 file_edit 工具的 description
- **THEN** description 包含"优先于 write 使用"或类似提示

#### Scenario: write 工具描述包含使用场景提示

- **WHEN** 模型阅读 file_write 工具的 description
- **THEN** description 包含"仅用于创建新文件"或类似提示

#### Scenario: grep 工具描述包含优先级提示

- **WHEN** 模型阅读 grep 工具的 description
- **THEN** description 包含"优先于 bash grep"或类似提示
