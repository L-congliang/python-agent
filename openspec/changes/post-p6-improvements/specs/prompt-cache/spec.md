## ADDED Requirements

### Requirement: System Prompt 缓存键生成
MimoClient SHALL 对 system prompt 计算 SHA-256 哈希，作为缓存键传递给 API。

#### Scenario: 相同 prompt 生成相同 cache key
- **WHEN** 连续两次调用使用相同的 system prompt
- **THEN** 两次的 cache_key 值相同

#### Scenario: 不同 prompt 生成不同 cache key
- **WHEN** 调用使用不同的 system prompt
- **THEN** 两次的 cache_key 值不同

### Requirement: API 不支持时优雅降级
如果 API 不支持 prompt_cache_key 参数，SHALL 不影响正常调用。

#### Scenario: API 忽略不支持的参数
- **WHEN** 传入 cache_key 但 API 不支持
- **THEN** 调用正常完成，不报错，不降级
