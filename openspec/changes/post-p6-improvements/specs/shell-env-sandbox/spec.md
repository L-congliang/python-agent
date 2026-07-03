## ADDED Requirements

### Requirement: Shell 环境变量白名单
bash 工具执行命令时，SHALL 只传递白名单内的环境变量给子进程，不传递完整环境。

#### Scenario: 白名单变量正常传递
- **WHEN** agent 调用 bash 执行 `echo $PATH`
- **THEN** 命令能正常执行，PATH 变量值正确

#### Scenario: 敏感变量不传递
- **WHEN** agent 调用 bash 执行 `env`
- **THEN** 输出中不包含 API_KEY、SECRET、TOKEN 等敏感变量

#### Scenario: Windows 系统变量保留
- **WHEN** 在 Windows 上执行 bash 命令
- **THEN** COMSPEC 和 SYSTEMROOT 变量正常传递，命令不因缺少系统变量而失败
