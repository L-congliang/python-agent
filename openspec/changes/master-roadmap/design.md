## Context

项目已有基线：
- Tool Protocol（Protocol 模式，15 属性，fail-closed 默认值）
- Agent Loop（流式调用 + 工具执行 + AbortController + 轮次保护）
- 7 个工具（Bash, Read, Write, Edit, Glob, Grep + 权限系统）
- 模型适配层（mimo + DeepSeek Adapter）
- CLI 终端 UI（Rich + Prompt Toolkit）
- 类型安全（mypy --strict，465 测试通过）
- 上下文压缩器（LLM 摘要，基础版）

参照项目 Pico（~6500 行核心代码）的架构，需要补齐评测、记忆、可观测性等能力。

约束：
- 不改变现有宏观架构（Tool Protocol、Agent Loop 不动）
- 代码质量标准：mypy --strict、测试覆盖
- 面向面试：每个设计决策要能讲清楚"为什么"

## Goals / Non-Goals

**Goals:**
- 建立可重复的自动化评测体系，每次改动有数据验证
- 实现预算制上下文管理，替代现有"超了才压缩"的模式
- 实现分层记忆系统，减少重复读取，提升长对话稳定性
- 实现工具错误恢复机制，生产级可靠性
- 实现 trace 和报告系统，让 agent 可调试
- 覆盖面试 6 个核心知识点

**Non-Goals:**
- 不做 UI 重构（CLI 已够用）
- 不做性能优化（先正确性后性能）
- 不做多模型并发（单模型足够）
- 不做生产部署（本地 CLI 工具）

## Decisions

### D1: 评测框架 — FakeModelClient 而非真实 API

**选择：** 用脚本化 FakeModelClient 做确定性测试。

**替代方案：**
- A) 用真实 API 测试 — 不确定性高、成本高、速度慢
- B) 用 mock 库（unittest.mock）— 无法测试完整的 prompt→response 流程

**理由：** FakeModelClient 模拟完整的 `complete(prompt) → response` 接口，测试确定性 100%，不调 API，速度快。真实 API 测试作为补充（P1），但不作为主力。

### D2: 上下文管理 — 预算制而非 LLM 摘要

**选择：** 按 section 分配 token 预算，超预算时按优先级裁剪。

**替代方案：**
- A) 继续用 LLM 摘要（现有 Compressor）— 增加延迟和成本，且摘要质量不可控
- B) 简单截断 — 丢失重要上下文

**理由：** 预算制是主动控制，LLM 摘要是被动补救。预算制能保证每次调用的 prompt 大小可控，且不需要额外的 API 调用。

**Section 优先级（从低到高）：**
1. history（历史消息）— 最先裁
2. tool_results（工具输出）— 其次裁
3. memory（工作记忆）— 再次裁
4. prefix（系统提示词）— 不裁
5. current_request（当前请求）— 不裁

### D3: 记忆系统 — 关键词检索而非向量检索

**选择：** 关键词 + 标签匹配检索。

**替代方案：**
- A) 向量数据库（ChromaDB/Pinecone）— 引入外部依赖，需要 embedding 模型
- B) 全文搜索（Elasticsearch）— 过重

**理由：** 本地 agent 的记忆数据量小（几十条笔记），关键词匹配足够。向量检索的优势在大数据量场景，这里不需要。如果未来需要语义检索，可以作为扩展点。

### D4: 可观测性 — 文件 trace 而非外部服务

**选择：** 本地 .agent/runs/ 目录存储 trace 和 report。

**替代方案：**
- A) 接入 LangSmith/Langfuse — 依赖外部服务
- B) 只打日志 — 结构化程度低，难以回放

**理由：** 本地文件存储零依赖，trace.jsonl 格式可以逐行解析，report.json 是完整的运行快照。面试时可以展示完整的可观测性设计。

### D5: 多 Agent — Registry + Router 模式

**选择：** Agent Registry 注册多个 agent，Router 根据意图分发。

**替代方案：**
- A) 单 agent 处理所有任务 — 简单但能力有限
- B) 编排框架（LangGraph）— 过重

**理由：** Registry + Router 是最简单的多 agent 模式，适合 CLI 工具。每个 agent 专注一个领域（coding / review / test），Router 做意图分类后分发。

### D6: MCP — 简化实现

**选择：** 实现 MCP 的核心协议（工具描述 + 调用 + 结果），不实现完整的 transport 层。

**替代方案：**
- A) 完整 MCP 实现 — 工作量大，超出实习项目范围
- B) 不做 MCP — 面试少一个知识点

**理由：** 面试需要能讲清楚 MCP 是什么、解决什么问题。简化实现（JSON-RPC over stdio）足以演示核心概念，不需要完整的 transport 和 discovery。

## Risks / Trade-offs

**[R1] 预算制可能过度裁剪重要上下文**
→ 缓解：Section Floor 机制保证每个 section 至少有最低预算。评测框架验证裁剪后 pass_rate 不降。

**[R2] FakeModelClient 无法覆盖真实模型的不确定性**
→ 缓解：FakeModelClient 测确定性逻辑（工具执行、状态流转），真实 API 测试（P1）覆盖模型交互。

**[R3] 关键词检索可能漏掉语义相关记忆**
→ 缓解：标签机制补充关键词不足。记忆条目少（<50 条），漏检率可控。

**[R4] 多 Agent 路由可能分发错误**
→ 缓解：Router 支持 fallback（分发失败时回退到默认 agent）。评测框架中的多 agent 任务验证分发准确率。

**[R5] 项目复杂度增加，测试维护成本上升**
→ 缓解：每个 Phase 独立测试，不交叉依赖。评测框架作为集成测试。
