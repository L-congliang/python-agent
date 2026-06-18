# 开发同步日志

跨地点开发时，记录每个地点的工作内容，让每次 session 都能快速了解上下文。

## 使用方式

在每次开发结束前，填写本次的工作记录。下次在另一个地点开始时，先读这个文件。

---

## 最新状态

- **当前功能**: F03 Tool Protocol + 注册系统（对齐 Claude Code）
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

### 2026-06-18 23:00 家

**做了什么:**
- **Claude Code 源码深度分析**
  - 读了泄露源码的核心模块（Tool.ts、query.ts、tools.ts、main.tsx 等）
  - 分析了 Tool 系统、主循环、权限系统、工具列表
  - 创建了 `docs/claude-code-architecture.md`（完整架构分析文档）
  - 明确了对齐目标：框架 100% 对齐，工具数量 30%

- **重写 F03 Tool Protocol spec**
  - 对齐 Claude Code 的 Tool 类型（30+ 属性，先实现 15 个核心）
  - 新增 ToolUseContext、PermissionDecision、ValidationResult
  - 新增 build_tool() 工厂函数（fail-closed 默认值）
  - 新增 validate_and_execute() 完整执行流程

- **新增 F04 Agent 主循环 spec**
  - 对齐 Claude Code 的 query.ts（68KB 核心循环）
  - 设计 AgentLoop class：流式调用→解析 tool_use→执行工具→注入结果→循环
  - 含中断支持（AbortController）、轮次保护（max_turns）

- **更新 feature_list.json 和 claude-progress.md**

**当前进度:**
- F01 status: done
- F02 status: pending（CLI 框架，后续做）
- F03 status: pending（spec 已重写，下一步实现）
- F04 status: pending（spec 已写，依赖 F03）
- F05-F10 status: pending

**下次从这里开始:**
1. 实现 F03 Tool Protocol（`tools/base.py` + `tools/registry.py` + `core/context.py`）
2. spec: `specs/F03-tool-protocol.md`
3. 关键任务：Tool Protocol + build_tool + ToolRegistry + 测试

**重要决策:**
- 先做 F03 再做 F02（工具系统是主循环的前置依赖）
- 对齐 Claude Code 框架（不是 demo 级别，而是工业级架构）
- fail-closed 默认值（安全第一）

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
