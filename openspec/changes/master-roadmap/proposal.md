## Why

当前项目已有 Tool Protocol、Agent Loop、7 个工具、权限系统、CLI 等基础模块（F01-F11），代码质量达标（mypy --strict、465 测试通过）。但要从"能跑的 demo"升级为"生产级 Agent"，缺少以下关键能力：

1. **没有评测体系** — 改了代码不知道是否真的变好了，全靠感觉
2. **上下文管理粗糙** — 现有 Compressor 是"超了才压缩"，没有预算制控制
3. **没有记忆系统** — agent 不记得之前读过什么文件，每次都重新读
4. **工具出错就崩** — 没有错误恢复机制，生产环境不可用
5. **没有可观测性** — 出错了不知道为什么，没法调试和优化

参照 Pico（同类型项目）的架构，需要补齐这些能力，同时覆盖面试所需的 6 个核心知识点：意图识别、MCP、多轮记忆、多 Agent 路由、监控评测、工具调用兜底。

## What Changes

- 新增评测框架（Benchmark + FakeModelClient + 自动指标）
- 重构上下文管理（从 LLM 摘要改为预算制 prompt 组装）
- 新增分层记忆系统（Working Memory + File Summaries + Episodic Notes + Retrieval）
- 新增工具鲁棒性层（错误恢复 + 重复调用拦截 + 路径逃逸防护）
- 新增可观测性系统（Trace 事件 + Run Report + Checkpoint）
- 新增多 Agent 能力（SubAgentTool + 子 Agent 隔离 + 上下文管理）
- 优化意图识别（System Prompt + Tool Description + Plan Mode）
- 新增 MCP 协议兼容层

## Capabilities

### New Capabilities

- `evaluation`: 评测框架 — Benchmark 定义、FakeModelClient、自动指标、回归对比
- `context-engineering`: 上下文工程 — 预算制 prompt 组装、section 分配、优先级裁剪
- `memory-system`: 分层记忆 — Working Memory、File Summaries、Episodic Notes、Retrieval、Durable Memory
- `tool-robustness`: 工具鲁棒性 — 错误恢复、重复调用拦截、路径逃逸防护、TaskState 状态机
- `observability`: 可观测性 — Trace 事件系统、Run Report、Checkpoint、会话持久化
- `multi-agent`: 多 Agent — SubAgentTool、子 Agent 隔离、上下文管理
- `intent-recognition`: 意图识别 — System Prompt 优化、Tool Description、Plan Mode
- `mcp-protocol`: MCP 协议 — 标准化工具描述、MCP Server、MCP Client

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- **代码结构**：新增 `evaluation/`、`memory/`、`observability/`、`persistence/`、`orchestration/` 模块
- **现有代码**：`context/compressor.py` 升级为 `context/context_manager.py`，`core/loop.py` 增加 trace 和 checkpoint 钩子
- **测试**：每个 Phase 新增对应测试，预计新增 200+ 测试用例
- **依赖**：可能引入 tiktoken（精确 token 计数）
- **目录结构**：新增 `.agent/` 运行时目录（sessions、runs、memory）
