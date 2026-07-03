## Why

当前 System Prompt 过于简陋——没有身份定义、没有行为准则、工具描述孤立、没有工具选择指南。模型需要自己推理"什么时候用什么工具"，对 mimo 这种推理能力较弱的模型来说，工具选择准确率不够高。此外缺少 Plan Mode，复杂任务直接开干不规划，容易出错。

## What Changes

- 优化 System Prompt 结构：加 Identity、Behavioral Guidelines、Tool Selection Guide
- 微调 Tool Description：在关键工具描述中加选择提示（如 edit 优先于 write）
- 实现 Plan Mode：用户触发 + 权限控制 + 纯文本计划输出
- 新增 Prompt Ablation Experiment：对比优化前后 prompt 的工具选择准确率
- 新增 Benchmark 对比：验证整体能力没有退化

## Capabilities

### New Capabilities

- `system-prompt-optimization`: System Prompt 结构化优化，包含 Identity、Behavioral Guidelines、Tool Selection Guide 三个模块
- `plan-mode`: Plan Mode 实现，用户触发 + 权限控制 + 计划输出与确认
- `prompt-ablation`: Prompt Ablation Experiment 实验框架，对比不同 prompt 版本的工具选择准确率

### Modified Capabilities

- `tool-description`: 微调现有工具的 description，加选择提示（如 edit 加"优先于 write 使用"）

## Impact

- `src/agent/core/loop.py` — `_build_system_prompt()` 方法重构
- `src/agent/tools/*.py` — 工具 description 微调
- `src/agent/permissions/checker.py` — 加 Plan Mode 支持
- `tests/` — 新增 prompt 优化、Plan Mode、ablation 实验的测试
- `docs/test-reports/` — 新增 P6 实验报告
