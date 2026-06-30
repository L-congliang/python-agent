## ADDED Requirements

### Requirement: Agent Registry

系统 SHALL 维护 Agent Registry，注册多个 agent，每个 agent 有：name、description、capabilities（能力标签）、system_prompt。

#### Scenario: 注册 agent

- **WHEN** 注册 coding_agent，capabilities=["code-edit", "code-search"]
- **THEN** Registry 中包含该 agent

#### Scenario: 列出 agent

- **WHEN** 查询 Registry
- **THEN** 返回所有已注册的 agent 及其 capabilities

### Requirement: 意图路由器

系统 SHALL 根据用户输入，将任务分发到最合适的 agent。路由逻辑：分析用户意图 → 匹配 agent capabilities → 选择最佳匹配。

#### Scenario: 代码编辑任务

- **WHEN** 用户说 "修复这个 bug"
- **THEN** 路由到 coding_agent

#### Scenario: 代码审查任务

- **WHEN** 用户说 "审查这个 PR"
- **THEN** 路由到 review_agent

#### Scenario: fallback

- **WHEN** 没有 agent 匹配用户意图
- **THEN** 路由到默认 agent（coding_agent）

### Requirement: Agent 间通信

系统 SHALL 支持 agent 之间传递上下文和结果。Agent A 可以将结果传给 Agent B 作为输入。

#### Scenario: 传递上下文

- **WHEN** coding_agent 完成代码修改，结果需要 review
- **THEN** coding_agent 的输出作为 review_agent 的输入

#### Scenario: 独立执行

- **WHEN** agent 不需要其他 agent 的结果
- **THEN** 独立执行，不等待其他 agent

### Requirement: 编排器

系统 SHALL 支持多 agent 顺序/并行执行的控制逻辑。编排器定义 agent 的执行顺序和依赖关系。

#### Scenario: 顺序执行

- **WHEN** 编排器定义 [coding_agent, review_agent]
- **THEN** coding_agent 先执行，完成后 review_agent 执行

#### Scenario: 并行执行

- **WHEN** 编排器定义 [test_agent_1, test_agent_2] 并行
- **THEN** 两个 agent 同时执行，等待全部完成
