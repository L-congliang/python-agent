# 开发同步日志

跨地点开发时，记录每个地点的工作内容，让每次 session 都能快速了解上下文。

## 使用方式

在每次开发结束前，填写本次的工作记录。下次在另一个地点开始时，先读这个文件。

---

## 最新状态

- **当前功能**: P2 记忆系统 V2 正式量化实验完成 — 三组差异仅 3.5%，效果不显著
- **最后更新**: 2026-07-06
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

### 2026-07-06 Session 29 — P2 记忆系统 V2 正式量化实验

**做了什么:**
- 冻结实验版本 `daf9a48` (Memory V2 + Evaluation V3)
- 修复 verifier 白名单 + MemoryManager.append_note() 参数传递
- Smoke test 通过后跑正式实验：3 组配置 × 5 轮 = 15 轮
- 生成 15 份单轮报告 + 1 份汇总报告

**实验结果:**
| Config | Clean | memory_dependent_success_rate |
|--------|-------|-------------------------------|
| memory_on | 5 | 96.00% |
| memory_off | 5 | 94.00% |
| memory_irrelevant | 4 | 97.50% |

**结论:** 当前 18 个任务 + mimo v2.5pro 模型下，记忆系统效果不显著。三组差异仅 3.5%，memory_irrelevant 反而最高。

**下一步:**
- 分析为什么记忆系统没有提供显著帮助
- 可能需要增加任务难度或设计更强的记忆依赖任务
- 考虑在能力较弱的模型上测试

---

### 2026-07-04 Session 23 — 编码修复 + 首轮真实评测

**做了什么:**
- 修复 Windows subprocess 编码问题（6 个文件：bash.py, grep.py, subagent.py, workspace.py, evaluator.py, model.py）
- MimoClient 429 重试增强（mimo 的 429 走 APIError 而非 RateLimitError）
- 实验框架加延迟（任务间 3s、配置间 5s）
- 三轮真实评测完成，结果见 `docs/test-reports/P2-memory-experiment.md`

**验证结果：**
- 全量测试：747 passed, 3 skipped
- 实验三轮稳定复现，但当前任务集太简单，无法体现记忆差异

**下一步：**
- 升级任务集，设计"不用记忆会吃亏"的 4 类任务
- 跨轮事实回忆、跨文件依赖修改、多轮连续改动、噪声干扰

### 2026-07-04 Session 21-22 — P2 记忆系统闭环 + 评测去假

**做了什么:**
- Phase 1：写路径闭环（loop.py +186 行）
  - LoopConfig 新增 memory_enabled 开关
  - run()/run_stream() 自动 set_task + try/finally save
  - _execute_tool_calls() 工具执行后自动写入记忆
  - 3 个 Bug 修复（子 Agent 开关继承、路径绝对化、freshness 误判）
- Phase 2：评测去假（memory_experiment.py 重写 + 34 个新测试）
  - tool_history 结构化工具执行历史
  - correct/repeated_reads/memory_hit 从硬编码改为真实统计
  - 6 个高质量任务（替代 12 个泛化任务）
  - memory_enabled 真开关替代 clear_session() 假关
  - 2 个 Bug 修复（setup_turns 污染 memory_hit、memory_irrelevant 假关闭）

**验证结果：**
- 全量测试：775 passed, 3 skipped

**当前进度:**
- P0-P6 全部 done
- 记忆系统：读路径 + 写路径 + 真实评测，完整闭环

**下次从这里开始:**
- 可以开始新功能，或对记忆系统做 Phase 3 优化（注入策略、freshness、子 Agent 隔离）

### 2026-07-02 Session 19 — P5 多 Agent 代码审查 + Bug 修复

**做了什么:**
- 深度审查 P5 多 Agent 系统全部代码（~1100 行，4 个模块）
- 逐模块讲解：agent_type.py → sub_agent.py → message_bus.py → subagent.py → loop.py 集成
- 发现并修复 2 个 Bug：
  1. `_find_parent_agent()` 返回 None — 给 ToolUseContext 加 agent_loop 字段
  2. SubAgentConstraints 每次新建 — 改为从父 Agent 继承
- 额外修复：parent_loop 赋值顺序、input 类型注解

**验证结果：**
- mypy --strict：改过的文件 0 错误
- 全量测试：709 passed, 3 skipped

**当前进度:**
- P0 (评测框架 + 基础能力) — ✅ done
- P1 (上下文工程) — ✅ done
- P2 (分层记忆系统) — ✅ done（已通过真实模型验证）
- P3 (工具鲁棒性) — ✅ done
- P4 (可观测性) — ✅ done
- P5 (多 Agent) — ✅ done（已修复 2 个 Bug）
- P6 — pending

**下次从这里开始:**
- P6 意图识别与 Prompt 工程（System Prompt 优化 + 意图分类）

### 2026-07-01 Session 18 — P4 可观测性

**做了什么:**
- 实现 P4 可观测性（8 个模块，39 个测试）
- 核心组件：
  - TraceEmitter（事件发射器，JSONL 格式）
  - RunReporter（运行报告生成）
  - CheckpointManager（断点续传 + freshness 检测）
  - Redactor（敏感信息脱敏）
  - WorkspaceSnapshot（工作区快照）
  - SessionStore（会话持久化）
  - RunStore（运行工件存储）
  - RecoveryExperiment（Recovery Ablation 实验）
- 集成到 AgentLoop
- 实现 Recovery Ablation 实验框架（10 个场景）

**当前进度:**
- P0 (评测框架 + 基础能力) — ✅ done
- P1 (上下文工程) — ✅ done
- P2 (分层记忆系统) — ✅ done（已通过真实模型验证）
- P3 (工具鲁棒性) — ✅ done
- P4 (可观测性) — ✅ done
- P5-P6 — pending

**P4 验证结果：**
- Recovery Ablation: resume_success_rate = 40%, enabled_success_rate = 40%, disabled_success_rate = 10%
- Benchmark: 605 passed, 3 skipped（未下降）
- pass_rate: 40%（与 Phase 3 一致）

**下次从这里开始:**
- P5 多 Agent 路由（AgentRegistry + 意图路由器 + 编排器）

---

### 2026-06-30 Session 17 — P3 工具鲁棒性

**做了什么:**
- 实现 P3 工具鲁棒性（5 个模块，24 个测试）
- 核心组件：
  - TaskState（状态机：running/completed/stopped/failed）
  - RepeatDetector（重复调用检测，连续 3 次拦截）
  - PathGuard（路径逃逸防护，解析符号链接）
  - RetryLimiter（重试上限，连续 5 次强制停止）
- 集成到 AgentLoop
- 实现 Security Experiment 实验框架（4 个场景）

**当前进度:**
- P0 (评测框架 + 基础能力) — ✅ done
- P1 (上下文工程) — ✅ done
- P2 (分层记忆系统) — ✅ done（已通过真实模型验证）
- P3 (工具鲁棒性) — ✅ done
- P4 (可观测性) — ✅ done
- P5-P6 — pending

### 2026-06-30 Session 16 — P2 分层记忆系统

**做了什么:**
- 实现 P2 分层记忆系统（7 个模块，29 个测试）
- 核心组件：
  - WorkingMemory（LRU 文件访问）
  - FileSummaries（180 字符摘要 + freshness 校验）
  - EpisodicNotes（12 条笔记 + 去重）
  - DurableMemory（跨 session 持久记忆）
  - Retrieval（标签 + 关键词检索）
  - MemoryRenderer（紧凑格式）
  - MemoryManager（统一接口）
- 集成到 AgentLoop
- 实现 Memory Experiment 实验框架

**当前进度:**
- P0 (评测框架 + 基础能力) — ✅ done
- P1 (上下文工程) — ✅ done
- P2 (分层记忆系统) — ✅ done（已通过真实模型验证）
- P3-P6 — pending

**P2 验证结果（真实模型）：**
- 工具调用减少 49%（20 vs 39 次）
- 耗时减少 61%（133s vs 340s）
- 正确率 100%

**下次从这里开始:**
- P3 工具鲁棒性（错误恢复 + 重复拦截 + 安全防护）

### 2026-06-30 Session 15 — 修复 Benchmark tool_steps=0 问题

**做了什么:**
- 修复 Benchmark 中 tool_steps 始终为 0 的问题
- 根本原因：System Prompt 缺少工具调用格式说明，模型不知道如何调用工具
- 修复内容：
  1. `tests/e2e_test.py` — 添加 `load_dotenv()` 加载 .env 文件
  2. `src/agent/core/model_adapter.py` — ToolCall 添加默认 id（uuid）
  3. `src/agent/core/loop.py` — 使用适配器生成的 id 而非空字符串
  4. `src/agent/evaluation/evaluator.py` — 改进 system prompt，告诉模型工具调用格式
  5. `benchmarks/run_benchmark.py` — 添加 `load_dotenv()` 加载 .env 文件
- Benchmark 结果：avg_tool_steps 从 0.0 提升到 2.0

**当前进度:**
- P0 (评测框架 + 基础能力) — ✅ done
- P1 (上下文工程) — ✅ done
- P2 (分层记忆系统) — ✅ done
- P3-P6 — pending

**下次从这里开始:**
- P3 工具鲁棒性（错误恢复 + 重复拦截 + 安全防护）
- 或用真实模型验证记忆系统效果

---

### 2026-06-23 Session 14 — F11 Glob 文件发现工具

**做了什么:**
- 实现 F11 Glob 文件发现工具（`tools/glob.py`，238 行）
  - pathlib.Path.glob() 实现，无外部依赖
  - 支持 **/*.py 等递归 glob 模式
  - 按修改时间排序（默认）/ 按路径排序
  - max_results 限制（默认 100）
- 更新 `tools/__init__.py` 导出 glob_tool
- 34 个测试全部通过
- 使用 GSD 工作流（plan-phase → execute-phase → code-review）

**当前进度:**
- F01-F11 status: done
- F12-F15 status: pending

**下次从这里开始:**
- F12 Sub-agent 派生（`core/subagent.py`）
- 需要先写 spec：`specs/F12-subagent.md`

---

### 2026-06-22 Session 13 — F10 上下文压缩器

**做了什么:**
- 实现 F10 上下文压缩器（`context/compressor.py`）
  - `ContextCompressor` 类：滑动窗口 + LLM 摘要
  - Token 追踪：从 API 响应提取 `usage` 字段
  - 自动压缩：`_total_tokens >= context_window * 0.8` 时触发
  - 保留策略：保留最近 30% 的 token
  - 降级策略：LLM 失败时返回原始文本前 500 字符
- 扩展 `core/model.py`：StreamResult 添加 `usage` 字段
- 扩展 `core/loop.py`：AgentLoop token 追踪和压缩检查
- 扩展 `cli/app.py`：添加 /compact 命令
- 24 个新测试全部通过（总计 431 passed）

**当前进度:**
- F01-F10 status: done
- F11-F15 status: pending

**下次从这里开始:**
- F11 Glob 文件查找（`tools/glob.py`）
- 需要先写 spec：`specs/F11-glob.md`

---

### 2026-06-21 Session 12 — F09 权限检查器

**做了什么:**
- 实现 F09 权限检查器（`permissions/checker.py`，163 行）
  - `PermissionMode` 枚举：default（正常）、plan（只读）
  - `check_system_policy()`：系统级策略判断
  - `PermissionChecker` 类：管理模式和策略判断
- 27 个测试全部通过
- 更新 `permissions/__init__.py` 导出新类型
- 创建 spec 文件（specs/F09-permission-checker.md）

**当前进度:**
- F01-F09 status: done
- F10-F15 status: pending

**下次从这里开始:**
- F10 上下文压缩（`context/compressor.py`）
- 需要先写 spec：`specs/F10-context-compressor.md`

---

### 2026-06-21 Session 11 — F08 搜索工具

**做了什么:**
- 使用 Superpowers brainstorming + writing-plans + subagent-driven-development 完成 F08 全流程
- 实现 Grep 工具（`tools/grep.py`）：ripgrep 封装，支持正则、文件过滤、路径指定等
- 80 个测试全部通过
- 更新 tools/__init__.py 导出 grep_tool
- 创建设计文档和实现计划（docs/superpowers/）

**当前进度:**
- F01-F08 status: done
- F09-F15 status: pending

**下次从这里开始:**
- F09 权限检查（`permissions/checker.py`）
- 需要先写 spec：`specs/F09-permission-checker.md`

---

### 2026-06-21 Session 10 — F07 文件写入工具

**做了什么:**
- 使用 Superpowers subagent-driven-development 完成 F07 全流程
- 实现 Write 工具（`tools/file_write.py`）：文本写入 + Notebook 写入
- 实现 Edit 工具（`tools/file_edit.py`）：局部替换 + replace_all 批量替换
- 102 个测试全部通过（Write 60 + Edit 42）
- 更新 tools/__init__.py 导出新工具

**当前进度:**
- F01-F07 status: done
- F08-F15 status: pending

**下次从这里开始:**
- F08 搜索工具（`tools/grep.py`）
- 需要先写 spec：`specs/F08-grep-tool.md`

---

### 2026-06-21 Session 9 — F06 文件读取工具

**做了什么:**
- 使用 Superpowers 全流程：brainstorming → writing-plans → subagent-driven-development
- 实现 F06 文件读取工具（`tools/file_read.py`，366 行）
  - 文本文件读取（行号、offset/limit、编码检测、缓存）
  - Jupyter Notebook 读取（JSON 解析、cell 格式化）
  - chardet 编码检测（UTF-8 优先 → chardet → latin-1）
  - FileReadState mtime 缓存（修改 `context.py`）
- 36 个测试全部通过
- 9 commits，含 2 个 review fix（截断顺序 bug、JSON 错误处理）

**当前进度:**
- F01-F07 status: done
- F08-F15 status: pending

**下次从这里开始:**
- F08 搜索工具（`tools/grep.py`）
- 需要先写 spec：`specs/F08-grep-tool.md`

---

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

### 2026-06-18 01:00 家

**做了什么:**
- **实现 F03 Tool Protocol**
  - 扩展 `core/types.py`：新增 PermissionDecision、ValidationResult、ToolResult
  - 旧 ToolResult（API 用）改名为 ToolCallResult，避免命名冲突
  - 新建 `core/context.py`：ToolUseContext、AbortController、FileReadState
  - 新建 `tools/base.py`：Tool Protocol（15 个属性/方法）+ build_tool() 工厂 + ToolImpl 实现类
  - 新建 `tools/registry.py`：ToolRegistry（注册、查询、to_anthropic_tools、validate_and_execute）
  - 更新 `core/__init__.py` 和 `tools/__init__.py` 导出

- **编写测试**
  - 新建 `tests/test_tool_protocol.py`：51 个测试
  - 覆盖：PermissionDecision、ValidationResult、AbortController、FileReadState、build_tool 默认值/覆盖、Tool 协议检查、ToolRegistry 注册/查询/过滤、to_anthropic_tools、validate_and_execute 完整流程
  - 全量测试 66 passed, 3 skipped

**当前进度:**
- F01 status: done
- F02 status: pending（CLI 框架）
- **F03 status: done** ✓
- F04 status: pending（下一步）
- F05-F10 status: pending

**下次从这里开始:**
1. 实现 F04 Agent 主循环（`core/loop.py`）
2. spec: `specs/F04-agent-loop.md`
3. 关键任务：AgentLoop class、消息构建、API 调用、tool_use 解析、工具执行、中断支持

**重要决策:**
- ToolResult 改名：旧的（API 用）→ ToolCallResult，新的（工具返回）→ ToolResult（对齐 Claude Code）
- ToolImpl 用 dataclass 实现，而不是闭包（更容易调试和序列化）

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

### 2026-06-18 Session 6 - F04 Agent 主循环

**改动文件**:
- src/agent/core/model.py (修改: 新增 StreamResult)
- src/agent/core/loop.py (新增: LoopConfig + AgentLoop)
- src/agent/core/__init__.py (修改: 更新导出)
- tests/test_model.py (修改: 适配新 API)
- tests/test_agent_loop.py (新增: 18 个测试)
- feature_list.json (修改: F04 done)
- claude-progress.md (修改: 添加 session 6)

**关键决策**: StreamResult 解决 tool_use 丢失; run() 内部用 chat_stream()

**测试**: 84 passed, 3 skipped

**下一步**: F02 CLI 或 F05-F10 工具
