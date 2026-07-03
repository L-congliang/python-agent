## ADDED Requirements

### Requirement: System Prompt Identity

系统 SHALL 在 system prompt 中包含 Identity 部分，定义 agent 身份和能力范围。

#### Scenario: Identity 包含角色定义

- **WHEN** `_build_system_prompt()` 构建 prompt
- **THEN** prompt 包含 agent 名称（Cool Code）和角色描述（终端 AI 编程助手）

#### Scenario: Identity 包含能力列表

- **WHEN** `_build_system_prompt()` 构建 prompt
- **THEN** prompt 包含可用能力列表（读写文件、搜索代码、执行命令、派生子 Agent）

### Requirement: System Prompt Behavioral Guidelines

系统 SHALL 在 system prompt 中包含 Behavioral Guidelines，包含通用原则和具体规则。

#### Scenario: 包含通用原则

- **WHEN** `_build_system_prompt()` 构建 prompt
- **THEN** prompt 包含至少 3 条通用原则（先理解再动手、最小改动、出错时分析原因）

#### Scenario: 包含具体规则

- **WHEN** `_build_system_prompt()` 构建 prompt
- **THEN** prompt 包含至少 3 条具体规则（改文件前必须先读、优先用 edit 不用 write、工具报错不要重复相同调用）

### Requirement: System Prompt Tool Selection Guide

系统 SHALL 在 system prompt 中包含 Tool Selection Guide，集中描述工具选择策略。

#### Scenario: Guide 包含工具选择映射

- **WHEN** `_build_system_prompt()` 构建 prompt
- **THEN** prompt 包含"要做什么 → 用什么工具"的映射表

#### Scenario: Guide 包含工具关系说明

- **WHEN** `_build_system_prompt()` 构建 prompt
- **THEN** prompt 包含工具优先级说明（如 edit 优先于 write，grep 优先于 bash grep）

### Requirement: System Prompt 模块化组装

系统 SHALL 将 system prompt 按模块组装，每个模块有明确职责。

#### Scenario: 模块按顺序拼接

- **WHEN** `_build_system_prompt()` 构建 prompt
- **THEN** 按 Identity → Behavior → Tool Guide → Dynamic Context 顺序拼接

#### Scenario: Dynamic Context 正确插入

- **WHEN** `_build_system_prompt()` 构建 prompt
- **THEN** memory.render() 和 SubAgent 使用指南作为 Dynamic Context 插入
