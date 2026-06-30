## ADDED Requirements

### Requirement: Trace 事件系统

系统 SHALL 在每个关键点 emit 事件。事件类型：prompt_built、model_requested、model_parsed、tool_executed、checkpoint_created、run_finished。每个事件包含时间戳和相关元数据。

#### Scenario: 记录 prompt 构建

- **WHEN** prompt 组装完成
- **THEN** emit prompt_built 事件，包含 prompt_metadata（各 section 大小、是否裁剪）

#### Scenario: 记录工具执行

- **WHEN** 工具执行完成
- **THEN** emit tool_executed 事件，包含工具名、参数、结果摘要、耗时

#### Scenario: 记录运行结束

- **WHEN** agent 停止
- **THEN** emit run_finished 事件，包含 status、stop_reason、final_answer、总耗时

### Requirement: Run Report

系统 SHALL 每次运行生成完整报告（report.json），包含：run_id、task_id、user_request、status、stop_reason、tool_steps、attempts、final_answer、checkpoint_id、duration_ms、prompt_metadata、completion_metadata。

#### Scenario: 生成报告

- **WHEN** agent 运行结束
- **THEN** 生成 .agent/runs/<run_id>/report.json

#### Scenario: 报告内容完整

- **WHEN** 读取 report.json
- **THEN** 包含所有必需字段

### Requirement: Checkpoint

系统 SHALL 在每个工具执行后创建 checkpoint 快照。Checkpoint 包含：当前目标、已完成步骤、关键文件及其 freshness、下一步计划。

#### Scenario: 创建 checkpoint

- **WHEN** 工具执行完成
- **THEN** 创建 checkpoint，记录关键文件的当前 hash

#### Scenario: freshness 检测

- **WHEN** 恢复 session 时检测到文件 freshness 变化
- **THEN** 标记 resume_status = partial-stale

#### Scenario: 恢复 checkpoint

- **WHEN** session 恢复且 freshness 一致
- **THEN** resume_status = full-valid，可以继续上次的任务

### Requirement: 会话持久化

系统 SHALL 将 session 持久化到 .agent/sessions/ 目录。Session 包含：id、created_at、workspace_root、history、memory。

#### Scenario: 保存 session

- **WHEN** agent 运行结束或创建 checkpoint
- **THEN** session 被保存到 .agent/sessions/<session_id>.json

#### Scenario: 加载 session

- **WHEN** 启动 agent 时指定 --resume
- **THEN** 从 .agent/sessions/ 加载最近的 session

### Requirement: 敏感信息脱敏

系统 SHALL 在 report 和 trace 中自动脱敏 API key、token、secret 等敏感信息。

#### Scenario: 脱敏 API key

- **WHEN** report 中包含 "api_key": "sk-abc123..."
- **THEN** 替换为 "api_key": "<redacted>"

#### Scenario: 脱敏环境变量

- **WHEN** trace 中包含环境变量 API_KEY=xxx
- **THEN** 替换为 API_KEY=<redacted>

### Requirement: Workspace 快照

系统 SHALL 在启动时捕获工作区状态：git 分支、最近 5 个提交、项目文档（README.md、pyproject.toml）。

#### Scenario: 捕获 git 信息

- **WHEN** agent 启动
- **THEN** 记录当前 git 分支和最近 5 个 commit message

#### Scenario: 加载项目文档

- **WHEN** 工作区有 README.md
- **THEN** 将 README.md 的前 200 行作为 workspace context 的一部分
