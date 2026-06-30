## ADDED Requirements

### Requirement: Token 精确计数

系统 SHALL 提供 TokenCounter，精确计算文本的 token 数量（替代现有的 len(text)//4 粗略估算）。

#### Scenario: 精确计数

- **WHEN** 对 "Hello, world!" 调用 TokenCounter.count()
- **THEN** 返回精确的 token 数量（非字符数/4）

#### Scenario: 空文本

- **WHEN** 对 "" 调用 TokenCounter.count()
- **THEN** 返回 0

### Requirement: Section 预算分配

系统 SHALL 将 prompt 分为 5 个 section，每个 section 有独立的 token 预算：prefix（系统提示词）、tools（工具描述）、memory（工作记忆）、history（历史消息）、current_request（当前请求）。

#### Scenario: 默认预算

- **WHEN** 使用默认配置
- **THEN** prefix 预算 3600、tools 预算 2000、memory 预算 1600、history 预算 5200、current_request 不限

#### Scenario: 自定义预算

- **WHEN** 配置 total_budget=8000
- **THEN** 各 section 预算按比例调整

### Requirement: 优先级裁剪

系统 SHALL 在 prompt 超出总预算时，按优先级裁剪各 section。裁剪顺序从低到高：history → tool_results → memory → tools → prefix。

#### Scenario: history 裁剪

- **WHEN** prompt 超出预算 500 token
- **THEN** 先裁剪 history，裁剪到 floor（最低保证）后才裁剪下一个 section

#### Scenario: floor 保护

- **WHEN** history 已裁剪到 floor（1500 token）
- **THEN** 不再裁剪 history，转而裁剪 tool_results

#### Scenario: prefix 不裁剪

- **WHEN** 所有可裁剪 section 都已到 floor
- **THEN** prefix 和 current_request 不被裁剪

### Requirement: Section Floor

系统 SHALL 为每个可裁剪 section 设置最低保证（floor），确保不会被完全裁掉。

#### Scenario: floor 生效

- **WHEN** history 预算 5200，floor 1500
- **THEN** history 最多被裁到 1500 token，不会更少

#### Scenario: floor 可配置

- **WHEN** 配置 section_floors={"history": 2000}
- **THEN** history 的 floor 变为 2000

### Requirement: 预算元数据

系统 SHALL 在每次 prompt 组装后，记录每个 section 的原始大小、裁剪后大小、是否触发裁剪。

#### Scenario: 记录元数据

- **WHEN** prompt 组装完成
- **THEN** metadata 包含每个 section 的 raw_chars、rendered_chars、was_truncated

#### Scenario: 无裁剪

- **WHEN** prompt 未超出预算
- **THEN** 所有 section 的 was_truncated = false
