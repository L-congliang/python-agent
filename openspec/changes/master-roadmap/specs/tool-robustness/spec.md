## ADDED Requirements

### Requirement: 错误恢复策略

系统 SHALL 在工具调用失败时，将错误信息注入到消息历史中，让模型决定重试或换工具。错误信息包含：工具名、错误类型、错误详情。

#### Scenario: 工具执行失败

- **WHEN** 工具执行抛出异常
- **THEN** 错误信息注入到消息历史，模型收到错误反馈

#### Scenario: 模型收到错误后换工具

- **WHEN** 模型收到 "file not found" 错误
- **THEN** 模型可以选择使用其他工具或返回最终答案

### Requirement: 重复调用拦截

系统 SHALL 检测同一工具同一参数的连续调用。连续 3 次相同调用 → 拦截并返回提示信息。

#### Scenario: 检测重复调用

- **WHEN** 模型连续 3 次调用 read_file(path="src/main.py")
- **THEN** 第 3 次调用被拦截，返回 "You've read this file 3 times. Try a different approach."

#### Scenario: 不同参数不算重复

- **WHEN** 模型调用 read_file(path="src/main.py") 和 read_file(path="src/utils.py")
- **THEN** 不触发重复检测

### Requirement: 路径逃逸防护

系统 SHALL 验证文件路径不能跳出工作区。路径解析后必须在 workspace root 内。

#### Scenario: 正常路径

- **WHEN** 文件路径为 "src/main.py"
- **THEN** 解析为 workspace_root/src/main.py，在工作区内

#### Scenario: 路径逃逸

- **WHEN** 文件路径为 "../outside.txt"
- **THEN** 返回错误 "Path escape detected: path is outside workspace"

#### Scenario: 符号链接

- **WHEN** 文件路径通过符号链接指向工作区外
- **THEN** 解析真实路径后检查，如果在工作区外则拒绝

### Requirement: 工具调用超时

系统 SHALL 为长时间运行的工具（如 Bash）设置超时保护。超时后强制终止工具执行。

#### Scenario: Bash 超时

- **WHEN** Bash 命令执行超过 30 秒
- **THEN** 强制终止进程，返回 "Command timed out after 30s"

#### Scenario: 超时可配置

- **WHEN** 配置 bash_timeout=60
- **THEN** Bash 工具超时时间为 60 秒

### Requirement: 重试上限

系统 SHALL 限制模型的连续重试次数。连续 5 次无效工具调用（格式错误、参数错误）→ 强制结束。

#### Scenario: 重试上限触发

- **WHEN** 模型连续 5 次返回格式错误的工具调用
- **THEN** 强制结束，返回 "Too many malformed responses. Stopping."

#### Scenario: 有效调用重置计数

- **WHEN** 模型在第 3 次无效调用后返回有效的工具调用
- **THEN** 无效调用计数重置为 0

### Requirement: TaskState 状态机

系统 SHALL 维护 TaskState，追踪任务状态流转：running → completed / stopped / failed。状态包含：run_id、task_id、user_request、status、tool_steps、attempts、stop_reason、final_answer。

#### Scenario: 成功完成

- **WHEN** 模型返回 final answer
- **THEN** status = completed，stop_reason = final_answer_returned

#### Scenario: 步数限制

- **WHEN** tool_steps 达到 max_steps
- **THEN** status = stopped，stop_reason = step_limit_reached

#### Scenario: 重试限制

- **WHEN** attempts 达到 max_attempts
- **THEN** status = stopped，stop_reason = retry_limit_reached

#### Scenario: 模型错误

- **WHEN** 模型 API 返回错误
- **THEN** status = failed，stop_reason = model_error
