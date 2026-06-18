# 进度日志

## Session 3 — 2026-06-18 公司（当前）

### 完成
- PRD 讨论：确认 CLI 形态 + mimo v2.5pro 模型
- 重写 F01-F03 specs 到实习项目级别（增加设计决策、面试问题、错误处理）
- 功能重新排序：F01 模型层 → F02 CLI → F03 Tool Protocol → F04 主循环...
- 更新 CLAUDE.md 项目定位和技术栈
- 更新 pyproject.toml 依赖（rich, prompt-toolkit, jsonschema）

### 当前状态
- 所有功能 status: pending，代码未开始
- F01-F03 spec 已完成，F04-F10 spec 待写
- harness 基础设施已完成

### 下次从这里开始
1. 实现 F01 `core/model.py`（mimo API 客户端）
2. 对应 spec: `specs/F01-model.md`
3. 关键任务：重试机制、错误分类、配置管理、日志记录

### 阻塞点
- （无）

---

## Session 2 — 2026-06-18 公司

### 完成
- 学习 OpenSpec，决定用手写 spec 方式
- 写了 F01 Tool Protocol spec（后来改为 F03）
- 更新 README 项目结构
- 添加 DEV_SYNC.md 跨地点同步机制

---

## Session 1 — 2026-06-18 家

### 完成
- 项目初始化，创建虚拟环境
- 修复 hatchling 构建错误（pyproject.toml 添加 wheel packages 配置）
- 搭建 harness 基础设施（CLAUDE.md, feature_list.json, Makefile, init.sh, claude-progress.md）
- 创建 types.py（6 个 dataclass：Role, ToolInput, ToolOutput, ToolCall, ToolResult, Message, StreamEvent）
- 学习 harness engineering 理念

### 下次从这里开始
- 写 F01 的 spec 文件
