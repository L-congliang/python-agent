## ADDED Requirements

### Requirement: Benchmark 定义

系统 SHALL 支持通过 JSON 文件定义标准测试任务。每个任务包含：id、prompt、fixture_repo（测试用的仓库快照）、allowed_tools（允许使用的工具）、step_budget（最大步数）、expected_artifact（期望产出）、verifier（验证脚本）、category（类别）。

#### Scenario: 加载 benchmark 任务

- **WHEN** 系统加载 benchmarks/coding_tasks.json
- **THEN** 返回任务列表，每个任务包含所有必需字段

#### Scenario: 验证任务格式

- **WHEN** 加载的 JSON 缺少必需字段
- **THEN** 抛出 ValueError 并指出缺失字段

### Requirement: FakeModelClient

系统 SHALL 提供 FakeModelClient，模拟模型后端的 complete(prompt, max_new_tokens) 接口。FakeModelClient 接受预定义的输出列表，每次调用返回下一个输出。

#### Scenario: 确定性输出

- **WHEN** FakeModelClient 初始化时传入 ["output1", "output2"]
- **WHEN** 调用 complete() 两次
- **THEN** 第一次返回 "output1"，第二次返回 "output2"

#### Scenario: 输出耗尽

- **WHEN** FakeModelClient 的输出列表为空时调用 complete()
- **THEN** 抛出 RuntimeError

#### Scenario: 记录输入

- **WHEN** 调用 FakeModelClient.complete(prompt, ...)
- **THEN** prompt 被记录到 FakeModelClient.prompts 列表

### Requirement: 任务执行器

系统 SHALL 支持执行 benchmark 任务：将任务的 prompt 传入 agent，执行 agent 的完整循环（prompt → model → tool → ... → final answer），记录每步操作。

#### Scenario: 执行单个任务

- **WHEN** 执行一个 step_budget=4 的任务
- **THEN** agent 在 4 步内完成，输出最终答案

#### Scenario: 超出步数限制

- **WHEN** agent 在 step_budget 步后仍未完成
- **THEN** 记录 stop_reason=step_limit_reached，任务标记为失败

### Requirement: 自动指标

系统 SHALL 自动计算以下指标：pass_rate（通过率）、avg_attempts（平均尝试次数）、avg_tool_steps（平均工具调用次数）、failure_category（失败类别分类）。

#### Scenario: 计算 pass_rate

- **WHEN** 10 个任务中 7 个通过
- **THEN** pass_rate = 70.0%

#### Scenario: 按类别统计

- **WHEN** 任务分为 file-edit、code-search、error-recovery 三个类别
- **THEN** 输出每个类别的 pass_rate

### Requirement: 回归对比

系统 SHALL 支持新旧版本对比：加载历史 benchmark 结果，与当前结果对比，输出 diff 报告。

#### Scenario: 对比新旧版本

- **WHEN** 旧版本 pass_rate=70%，新版本 pass_rate=75%
- **THEN** 报告显示 pass_rate 提升 5%

#### Scenario: 新版本退化

- **WHEN** 旧版本 pass_rate=70%，新版本 pass_rate=65%
- **THEN** 报告显示 pass_rate 下降 5%，标记为退化
