## Phase 0: 评测框架 + 基础能力 ✅

### 评测框架
- [x] 0.1 创建 `src/agent/evaluation/` 模块结构
- [x] 0.2 实现 FakeModelClient（脚本化输出、记录输入、输出耗尽处理）
- [x] 0.3 实现 Benchmark 定义加载器（JSON 解析、格式验证、必需字段检查）
- [x] 0.4 创建 10 个标准测试任务（benchmarks/coding_tasks.json）+ fixtures
- [x] 0.5 实现任务执行器（prompt → agent → 记录每步 → 验证结果）
- [x] 0.6 实现自动指标计算（pass_rate、avg_attempts、avg_tool_steps、failure_category）
- [x] 0.7 实现回归对比报告（新旧版本对比、diff 输出）
- [x] 0.8 编写评测框架测试
- [x] 0.9 运行 benchmark，输出基线数据

### 基础能力（F01-F11）
- [x] 模型层（MimoClient + ModelAdapter + MimoAdapter）
- [x] CLI 框架（rich + prompt_toolkit）
- [x] Tool Protocol + 注册系统
- [x] Agent 主循环
- [x] 工具集（Bash、文件读写编辑、Grep、Glob）
- [x] 权限检查
- [x] 上下文压缩

### Benchmark 结果（基线）
- pass_rate: 40%
- avg_tool_steps: 2.0
- avg_attempts: 2.6

## Phase 1: 上下文工程

### 核心实现
- [x] 1.1 实现 TokenCounter（精确 token 计数，替代 len(text)//4）
- [x] 1.2 定义 Section 预算配置（prefix/tools/memory/history/current_request）
- [x] 1.3 实现 ContextManager（预算制 prompt 组装）
- [x] 1.4 实现优先级裁剪（history → tool_results → memory → tools → prefix）
- [x] 1.5 实现 Section Floor（最低保证）
- [x] 1.6 实现预算元数据记录
- [x] 1.7 将 AgentLoop 集成 ContextManager
- [x] 1.8 编写上下文管理测试

### Context Ablation 实验
- [x] 1.9 实现 Context Ablation 实验框架
  - 测试不同 history/note/request 长度组合
  - 对比 full vs no_context_reduction
  - 计算 compression_ratio、current_request_preserved_rate
- [x] 1.10 运行 Context Ablation 实验
- [x] 1.11 运行 benchmark 对比 Phase 0 基线

### 验证指标
- avg_prompt_compression_ratio（压缩比）
- current_request_preserved_rate（当前请求保留率）
- pass_rate 不能下降

## Phase 2: 分层记忆系统

### 核心实现
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

### Memory Experiment 实验
- [ ] 2.11 实现 Memory Experiment 实验框架
  - 测试 memory_on vs memory_off vs memory_irrelevant
  - 记录 repeated_reads、correct_rate、memory_hit_rate
  - 12 个标准任务（fact_lookup、edit_dependency、history_reference）
- [ ] 2.12 运行 Memory Experiment 实验
- [ ] 2.13 运行 benchmark 对比 Phase 1

### 验证指标
- repeated_reads（重复读取次数，越少越好）
- correct_rate（正确率）
- memory_hit_rate（记忆命中率）

## Phase 3: 工具鲁棒性

### 核心实现
- [ ] 3.1 实现错误恢复策略（错误信息注入消息历史）
- [ ] 3.2 实现重复调用拦截（同一工具同一参数连续 3 次 → 拦截）
- [ ] 3.3 实现路径逃逸防护（文件路径不能跳出工作区）
- [ ] 3.4 实现工具调用超时（Bash 等工具超时保护）
- [ ] 3.5 实现重试上限（连续 5 次无效调用 → 强制结束）
- [ ] 3.6 实现 TaskState 状态机（running/completed/stopped/failed）
- [ ] 3.7 将 AgentLoop 集成 TaskState
- [ ] 3.8 编写工具鲁棒性测试

### Security Experiment 实验
- [ ] 3.9 实现 Security Experiment 实验框架
  - 10 个安全场景（path_escape、symlink_escape、search_escape、approval_denied、read_only_write、repeated_call 等）
  - 记录 security_event_counts、tool_error_code_counts
- [ ] 3.10 运行 Security Experiment 实验
- [ ] 3.11 运行 benchmark 对比 Phase 2

### 验证指标
- security_event_counts（安全事件拦截次数）
- tool_error_code_counts（工具错误码统计）
- pass_rate 不能下降

## Phase 4: 可观测性

### 核心实现
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

### Recovery Ablation 实验
- [ ] 4.12 实现 Recovery Ablation 实验框架
  - 10 个恢复场景（checkpoint_resume、partial_stale、workspace_mismatch、schema_mismatch、partial_success）
  - 测试 resume_enabled vs resume_disabled
  - 记录 resume_success_rate、stale_reanchor_rate、workspace_drift_detection_rate、resume_false_accept_rate
- [ ] 4.13 运行 Recovery Ablation 实验
- [ ] 4.14 运行 benchmark 对比 Phase 3

### 验证指标
- resume_success_rate（恢复成功率）
- stale_reanchor_rate（过期重新锚定率）
- workspace_drift_detection_rate（工作区漂移检测率）
- resume_false_accept_rate（误接受率，越低越好）

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
