## Phase 0: 评测框架

- [x] 0.1 创建 `src/agent/evaluation/` 模块结构
- [x] 0.2 实现 FakeModelClient（脚本化输出、记录输入、输出耗尽处理）
- [x] 0.3 实现 Benchmark 定义加载器（JSON 解析、格式验证、必需字段检查）
- [x] 0.4 创建 10 个标准测试任务（benchmarks/coding_tasks.json）+ fixtures
- [x] 0.5 实现任务执行器（prompt → agent → 记录每步 → 验证结果）
- [x] 0.6 实现自动指标计算（pass_rate、avg_attempts、avg_tool_steps、failure_category）
- [x] 0.7 实现回归对比报告（新旧版本对比、diff 输出）
- [x] 0.8 编写评测框架测试
- [x] 0.9 运行 benchmark，输出基线数据

## Phase 1: 上下文工程

- [ ] 1.1 实现 TokenCounter（精确 token 计数，替代 len(text)//4）
- [ ] 1.2 定义 Section 预算配置（prefix/tools/memory/history/current_request）
- [ ] 1.3 实现 ContextManager（预算制 prompt 组装）
- [ ] 1.4 实现优先级裁剪（history → tool_results → memory → tools → prefix）
- [ ] 1.5 实现 Section Floor（最低保证）
- [ ] 1.6 实现预算元数据记录
- [ ] 1.7 将 AgentLoop 集成 ContextManager
- [ ] 1.8 编写上下文管理测试
- [ ] 1.9 运行 benchmark 对比 Phase 0 基线

## Phase 2: 分层记忆系统

- [ ] 2.1 创建 `src/agent/memory/` 模块结构
- [ ] 2.2 实现 WorkingMemory（task_summary + recent_files LRU）
- [ ] 2.3 实现 FileSummaries（摘要生成 + freshness 校验）
- [ ] 2.4 实现 EpisodicNotes（带时间戳和标签的笔记）
- [ ] 2.5 实现 Retrieval（关键词 + 标签匹配检索）
- [ ] 2.6 实现记忆渲染（给模型看的紧凑格式）
- [ ] 2.7 实现 DurableMemory（跨 session 持久记忆）
- [ ] 2.8 实现晋升机制（工作记忆 → 持久记忆）
- [ ] 2.9 将 AgentLoop 集成记忆系统
- [ ] 2.10 编写记忆系统测试
- [ ] 2.11 运行 benchmark 对比 Phase 1

## Phase 3: 工具鲁棒性

- [ ] 3.1 实现错误恢复策略（错误信息注入消息历史）
- [ ] 3.2 实现重复调用拦截（同一工具同一参数连续 3 次 → 拦截）
- [ ] 3.3 实现路径逃逸防护（文件路径不能跳出工作区）
- [ ] 3.4 实现工具调用超时（Bash 等工具超时保护）
- [ ] 3.5 实现重试上限（连续 5 次无效调用 → 强制结束）
- [ ] 3.6 实现 TaskState 状态机（running/completed/stopped/failed）
- [ ] 3.7 将 AgentLoop 集成 TaskState
- [ ] 3.8 编写工具鲁棒性测试
- [ ] 3.9 运行 benchmark 对比 Phase 2

## Phase 4: 可观测性

- [ ] 4.1 创建 `src/agent/observability/` 模块结构
- [ ] 4.2 实现 Trace 事件系统（prompt_built/model_requested/tool_executed/run_finished）
- [ ] 4.3 实现 Run Report 生成（report.json）
- [ ] 4.4 实现 Checkpoint 系统（每步快照 + freshness 检测）
- [ ] 4.5 创建 `src/agent/persistence/` 模块结构
- [ ] 4.6 实现 SessionStore（会话持久化到 .agent/sessions/）
- [ ] 4.7 实现 RunStore（运行工件存储到 .agent/runs/）
- [ ] 4.8 实现敏感信息脱敏（API key、token 等自动脱敏）
- [ ] 4.9 实现 Workspace 快照（git 分支、最近提交、项目文档）
- [ ] 4.10 将 AgentLoop 集成 trace/checkpoint
- [ ] 4.11 编写可观测性测试
- [ ] 4.12 运行 benchmark 对比 Phase 3

## Phase 5: 多 Agent 路由

- [ ] 5.1 创建 `src/agent/orchestration/` 模块结构
- [ ] 5.2 实现 AgentRegistry（注册多个 agent）
- [ ] 5.3 实现意图路由器（用户意图 → agent capabilities 匹配）
- [ ] 5.4 实现 Agent 间通信（上下文和结果传递）
- [ ] 5.5 实现编排器（顺序/并行执行控制）
- [ ] 5.6 实现 Sub-Agent（spawn 子 agent）
- [ ] 5.7 编写多 Agent 测试
- [ ] 5.8 运行 benchmark 对比 Phase 4

## Phase 6: 意图识别与 Prompt 工程

- [ ] 6.1 优化 System Prompt（结构化、包含工具指南）
- [ ] 6.2 优化 Tool Description（精准描述、示例）
- [ ] 6.3 实现意图分类（code-edit/code-search/question/chat）
- [ ] 6.4 实现 Plan Mode（先规划再执行）
- [ ] 6.5 编写意图识别测试
- [ ] 6.6 运行 benchmark 对比 Phase 5

## Phase 7: MCP 协议兼容

- [ ] 7.1 实现 MCP 工具描述转换（内部工具 → MCP 格式）
- [ ] 7.2 实现 MCP Server（stdio transport、JSON-RPC）
- [ ] 7.3 实现 MCP Client（连接第三方 MCP Server）
- [ ] 7.4 实现协议版本协商（2024-11-05）
- [ ] 7.5 编写 MCP 测试
- [ ] 7.6 运行 benchmark 对比 Phase 6

## Phase 8: 部署与交付

- [ ] 8.1 配置 pyproject.toml（打包、入口点）
- [ ] 8.2 配置 CLI 入口（`python -m agent` 或 `agent` 命令）
- [ ] 8.3 配置管理（.env + 命令行参数 + 配置文件）
- [ ] 8.4 更新 README（面向面试官的项目说明）
- [ ] 8.5 最终 benchmark 运行，输出完整指标
