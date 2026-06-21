# 简历亮点 - AI 编程助手项目

> 本文档记录项目中可以写到简历上的技术亮点，实时更新。
> 最后更新：2026-06-21（F07 完成）

---

## 一句话版本（简历项目描述）

**AI 编程助手（类 Claude Code）** | Python, Anthropic SDK, Rich
- 对齐 Claude Code 架构，实现 Tool Protocol、Agent 主循环、文件读写工具
- 支持流式输出、权限控制、缓存优化，300+ 测试用例覆盖

---

## 详细版本（面试讲解用）

### 项目概述

一个类 Claude Code 的 CLI AI 编程助手，使用 mimo v2.5pro 模型（国产大模型）。
目标是构建工业级架构，不是 demo 级别的玩具。

### 核心技术亮点

#### 1. Tool Protocol 工具协议（F03）

**做了什么：**
- 设计 15 属性的 Tool Protocol 接口，对齐 Claude Code 源码
- 实现 `build_tool()` 工厂函数，统一工具创建流程
- 实现 `validate_and_execute()` 5 步执行流程（查找→启用→校验→权限→执行）

**技术点：**
- Protocol 类型定义（Python 3.12+）
- 工厂模式 + 闭包
- fail-closed 安全默认值

**可以讲的设计决策：**
- 为什么用 Protocol 而不是简单字典映射？→ 可扩展性、类型安全
- 为什么 5 步执行流程？→ 每步失败都能返回具体错误给模型
- 为什么 fail-closed？→ 安全第一，默认不并发、不只读

#### 2. Agent 主循环（F04）

**做了什么：**
- 实现 `AgentLoop` 类：流式调用→解析 tool_use→执行工具→注入结果→循环
- 支持中断（AbortController）、轮次保护（max_turns）
- 同步 `run()` 和流式 `run_stream()` 两种模式

**技术点：**
- Anthropic SDK 流式 API
- Generator + Iterator 模式
- 消息历史管理

**可以讲的设计决策：**
- 为什么同时提供 run() 和 run_stream()？→ 不同场景需要不同接口
- StreamResult 如何解决 tool_use 丢失问题？→ 流结束后获取完整 content blocks

#### 3. 文件工具系统（F05/F06/F07）

**做了什么：**
- **Bash 工具**：执行系统命令，支持超时、工作目录、输出截断
- **Read 工具**：读取文件，支持行号、offset/limit、编码检测、Notebook
- **Write 工具**：创建/覆盖文件，自动创建目录、权限检查、磁盘空间检查
- **Edit 工具**：精确替换，唯一匹配约束、replace_all 支持

**技术点：**
- chardet 编码检测（UTF-8 优先 → chardet → latin-1 fallback）
- mtime 缓存策略（避免重复磁盘 I/O）
- Windows 兼容（os.statvfs → shutil.disk_usage）
- mypy --strict 类型安全

**可以讲的设计决策：**
- 为什么 Read 要带行号？→ 模型可以精确引用"第 X 行"
- 为什么 Write/Edit 分开？→ 职责清晰，Write 整体覆盖，Edit 局部替换
- 为什么 old_string 必须唯一匹配？→ 防止误替换
- 为什么要缓存？→ 同一次对话可能多次读同一文件

#### 4. CLI 终端 UI（F02）

**做了什么：**
- 使用 Rich + Prompt Toolkit 构建终端界面
- 流式渲染（缓冲策略：chunk 攒着，遇换行渲染）
- 工具面板、Markdown 渲染、语法高亮

**技术点：**
- Rich 库（Markdown、Panel、Table、Syntax）
- 事件驱动回调模式
- 流式缓冲策略

### 量化数据

| 指标 | 数值 |
|------|------|
| 测试用例 | 300+ |
| 测试覆盖率 | 核心路径 100% |
| 类型检查 | mypy --strict 0 错误 |
| 工具数量 | 4 个（Bash, Read, Write, Edit） |
| 代码行数 | ~2000 行（核心模块） |

### 项目结构

```
src/agent/
├── core/           # 核心模块
│   ├── model.py    # 模型层（Anthropic SDK 封装）
│   ├── loop.py     # Agent 主循环
│   ├── types.py    # 类型定义
│   └── context.py  # 上下文管理
├── tools/          # 工具系统
│   ├── base.py     # Tool Protocol
│   ├── registry.py # 工具注册表
│   ├── bash.py     # Bash 工具
│   ├── file_read.py    # 文件读取
│   ├── file_write.py   # 文件写入
│   └── file_edit.py    # 文件编辑
├── permissions/    # 权限控制
├── context/        # 上下文管理
└── cli/            # 终端 UI
    └── app.py      # AgentApp
```

---

## 面试常见问题

### Q: 为什么选择对齐 Claude Code？

**A:** Claude Code 是业界标杆，架构设计经过验证。对齐它的架构可以：
1. 学习工业级 Agent 的设计思路
2. 代码质量有保障，不是 demo 级别
3. 面试时有明确的参照物，方便讲解

### Q: 遇到了什么技术难点？

**A:**
1. **流式输出中 tool_use 丢失**：Anthropic SDK 的 `text_stream` 只返回文本，tool_use block 不在其中。解决：流结束后调用 `get_final_message()` 获取完整 content blocks。

2. **Windows 兼容性**：`os.statvfs` 在 Windows 不存在。解决：改用 `shutil.disk_usage`，跨平台兼容。

3. **mypy --strict 类型检查**：`dict.get()` 返回 `Any | None`，类型不安全。解决：改用 `input["key"]: str = ...` 模式。

4. **文件编码检测**：中文项目经常遇到 GBK 编码，直接用 UTF-8 会报错。解决：UTF-8 优先 → chardet 检测 → latin-1 兜底。

### Q: 这个项目和市面上的 AI 助手有什么区别？

**A:**
1. **开源可学习**：代码结构清晰，适合学习 Agent 架构
2. **国产模型**：使用 mimo v2.5pro，不依赖 OpenAI
3. **工业级架构**：不是 demo，对齐 Claude Code 的设计标准
4. **完整工具系统**：权限控制、缓存优化、类型安全

### Q: 如果让你继续做，下一步做什么？

**A:**
- F08: 搜索工具（grep）- 代码搜索能力
- F09: 文件浏览工具（glob）- 文件发现能力
- F10: 上下文管理 - 对话历史压缩
- F11: 权限系统 - 细粒度权限控制
- 最终目标：完整的 CLI Agent，可以独立完成编程任务

---

## 技术栈关键词（简历 ATS 优化）

**编程语言：** Python 3.12+

**AI/ML：** Anthropic SDK, LLM, Agent, 流式输出, 工具调用

**架构设计：** Protocol, 工厂模式, 闭包, 事件驱动, 组件化

**工程实践：** mypy --strict, pytest, TDD, 类型安全, 缓存优化

**终端开发：** Rich, Prompt Toolkit, CLI, Markdown 渲染

**跨平台：** Windows/Linux/Mac 兼容

---

## 更新日志

### 2026-06-21 - F07 完成
- ✅ 添加 Write/Edit 工具到简历
- ✅ 添加缓存一致性、权限检查等技术点
- ✅ 更新量化数据（300+ 测试）

### 2026-06-21 - F06 完成
- ✅ 添加 Read 工具到简历
- ✅ 添加编码检测、mtime 缓存等技术点

### 2026-06-20 - F05 完成
- ✅ 添加 Bash 工具到简历
- ✅ 添加 subprocess、超时控制等技术点

### 2026-06-18 - F03/F04 完成
- ✅ 添加 Tool Protocol 和 Agent 主循环
- ✅ 添加核心架构设计

---

## 待补充（项目进展后更新）

- [ ] F08 搜索工具（grep）- 代码搜索能力
- [ ] F09 文件浏览工具（glob）- 文件发现能力
- [ ] F10 上下文管理 - 对话历史压缩
- [ ] F11 权限系统 - 细粒度权限控制
- [ ] 性能优化 - 并发执行、缓存命中率
- [ ] 集成测试 - 端到端测试场景
