## ADDED Requirements

### Requirement: Prompt Ablation 实验框架

系统 SHALL 支持 Prompt Ablation Experiment，对比不同 prompt 版本的工具选择准确率。

#### Scenario: 支持多配置对比

- **WHEN** 运行 Prompt Ablation Experiment
- **THEN** 支持对比 baseline / +identity / +tool_guide / +full 四个配置

#### Scenario: 测试任务集

- **WHEN** 运行 Prompt Ablation Experiment
- **THEN** 使用包含至少 20 个任务的测试集，覆盖所有工具类型

### Requirement: 工具选择准确率指标

系统 SHALL 记录每个配置的工具选择准确率。

#### Scenario: 记录 first_try_accuracy

- **WHEN** 实验完成
- **THEN** 记录每个配置的 first_try_accuracy（第一次就选对工具的比例）

#### Scenario: 记录 tool_accuracy

- **WHEN** 实验完成
- **THEN** 记录每个配置的 tool_accuracy（最终选对工具的比例）

#### Scenario: 记录 prompt 长度

- **WHEN** 实验完成
- **THEN** 记录每个配置的平均 prompt token 数

### Requirement: 实验报告生成

系统 SHALL 生成实验报告到 docs/test-reports/ 目录。

#### Scenario: 报告包含对比表格

- **WHEN** 实验完成
- **THEN** 报告包含 4 个配置的指标对比表格

#### Scenario: 报告包含结论

- **WHEN** 实验完成
- **THEN** 报告包含实验结论和最优配置推荐
