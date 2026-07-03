## ADDED Requirements

### Requirement: pip install 后可用 agent 命令
执行 `pip install .` 后，SHALL 在 PATH 中生成 `agent` 命令，直接启动 CLI。

#### Scenario: pip install 生成入口命令
- **WHEN** 用户执行 `pip install .`
- **THEN** `agent` 命令可用，等同于 `python -m agent`

#### Scenario: agent 命令启动完整功能
- **WHEN** 用户在终端执行 `agent`
- **THEN** 启动 AgentApp REPL，显示欢迎界面，功能与 `python -m agent` 一致
