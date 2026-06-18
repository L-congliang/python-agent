# 开发同步日志

跨地点开发时，记录每个地点的工作内容，让每次 session 都能快速了解上下文。

## 使用方式

在每次开发结束前，填写本次的工作记录。下次在另一个地点开始时，先读这个文件。

---

## 最新状态

- **当前功能**: F01 模型层 - mimo API
- **最后更新**: 2026-06-18 23:20
- **最后地点**: 公司
- **当前所在地**: 公司（准备回家）

---

## 工作日志

### 2026-06-18 23:15 公司

**做了什么:**
- PRD 讨论：确认发布形态为 CLI，使用 mimo v2.5pro 模型
- 重新规划功能顺序（F01 模型层 → F02 CLI → F03 Tool Protocol...）
- 写了 F01 模型层 spec、F02 CLI spec
- 更新 pyproject.toml 添加 rich、prompt-toolkit 依赖

**当前进度:**
- F01 spec 已写完，代码未开始
- F02 spec 已写完，代码未开始
- F03 spec 已有（原 F01）

**下次从这里开始:**
- 实现 F01 core/model.py（连接 mimo API）
- mimo API 地址: https://token-plan-cn.xiaomimimo.com/anthropic
- API key 已在 spec 中记录

**备注:**
- 只用 mimo 模型，不需要兼容 Claude API

---

### 2026-06-18 22:30 家

**做了什么:**
- 搭建 harness 基础设施 (CLAUDE.md, feature_list.json, Makefile, init.sh)
- 学习 harness engineering 理念，参考 learn-harness-engineering 仓库
- 学习 OpenSpec，决定先用手写 spec 的方式
- 写了 F01 Tool Protocol 的 spec 文件
- 更新 README 项目结构
- 添加 DEV_SYNC.md 跨地点同步机制

**当前进度:**
- F01 spec 已写完，代码未开始
- 类型基础 (types.py) 已有

**下次从这里开始:**
- 实现 F01 tools/base.py (Tool Protocol)
- 对应 spec: specs/F01-tool-protocol.md

**备注:**
- （无）

---

<!-- 模板：复制下面的内容填写新的记录 -->

<!--
### YYYY-MM-DD HH:MM 地点

**做了什么:**
- （具体做了什么）

**当前进度:**
- （做到哪了）

**下次从这里开始:**
- （下一步做什么）

**备注:**
- （可选：遇到的问题、阻塞点、想法）
-->
