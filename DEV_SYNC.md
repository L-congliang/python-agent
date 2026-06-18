# 开发同步日志

跨地点开发时，记录每个地点的工作内容，让每次 session 都能快速了解上下文。

## 使用方式

在每次开发结束前，填写本次的工作记录。下次在另一个地点开始时，先读这个文件。

---

## 最新状态

- **当前功能**: F02 CLI 框架 - 终端 UI
- **最后更新**: 2026-06-18
- **最后地点**: 家
- **当前所在地**: 家

---

## 关键技术决策（不会变的）

- **模型**: 只用 mimo v2.5pro，不需要兼容 Claude API
- **API**: `https://token-plan-cn.xiaomimimo.com/anthropic`，用 Anthropic SDK 调用
- **形态**: CLI 工具，用 rich + prompt_toolkit
- **定位**: 实习项目，不是 demo，代码质量要能面试讲解

---

## 工作日志

### 2026-06-18 家

**做了什么:**
- 实现 F01 模型层（core/model.py）
  - MimoClient + ModelConfig + load_config
  - 同步/流式对话、重试机制、错误处理、日志
- 编写测试（tests/test_model.py）：15 个测试通过
- 创建 LEARNING_NOTES.md 学习笔记
- 更新 core/__init__.py 导出新模块

**当前进度:**
- F01 status: done
- F02-F10 status: pending
- F01-F03 spec 已完成，F04-F10 spec 待写

**下次从这里开始:**
- 实现 F02 CLI 框架（cli/app.py）
- spec: `specs/F02-cli.md`
- 关键任务：rich 渲染 + prompt_toolkit 交互

**备注:**
- 集成测试需要设置 MIMO_API_KEY 环境变量

---

### 2026-06-18 22:30 家

**做了什么:**
- 搭建 harness 基础设施
- 学习 harness engineering
- 添加 DEV_SYNC.md

**当前进度:**
- harness 完成，代码未开始

---

<!-- 模板 -->
<!--
### YYYY-MM-DD HH:MM 地点

**做了什么:**
-

**当前进度:**
-

**下次从这里开始:**
-

**备注:**
-
-->
