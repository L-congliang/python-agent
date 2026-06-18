# 开发同步日志

跨地点开发时，记录每个地点的工作内容，让每次 session 都能快速了解上下文。

## 使用方式

在每次开发结束前，填写本次的工作记录。下次在另一个地点开始时，先读这个文件。

---

## 最新状态

- **当前功能**: F01 模型层 - mimo API 客户端
- **最后更新**: 2026-06-18 23:40
- **最后地点**: 公司
- **当前所在地**: 公司（准备回家）

---

## 关键技术决策（不会变的）

- **模型**: 只用 mimo v2.5pro，不需要兼容 Claude API
- **API**: `https://token-plan-cn.xiaomimimo.com/anthropic`，用 Anthropic SDK 调用
- **形态**: CLI 工具，用 rich + prompt_toolkit
- **定位**: 实习项目，不是 demo，代码质量要能面试讲解

---

## 工作日志

### 2026-06-18 23:40 公司

**做了什么:**
- PRD 讨论：确认 CLI 形态 + mimo v2.5pro
- 重写 F01-F03 specs 到实习项目级别
- 更新 CLAUDE.md 项目定位、技术栈、完成标准
- 更新 pyproject.toml 依赖

**当前进度:**
- F01-F03 spec 已完成，代码未开始
- 所有功能 status: pending

**下次从这里开始:**
- 实现 F01 `core/model.py`（mimo API 客户端）
- spec: `specs/F01-model.md`
- 先 `pip install -e ".[dev]"` 安装依赖

**备注:**
- （无）

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
