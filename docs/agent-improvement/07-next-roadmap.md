# 下一步路线

## 已完成

### Phase 2.2：Observation / Context Compression Hardening

- 统一 Observation Budget 契约（ToolResult + ObservationMetadata）
- 工具层输出截断与 Artifact 化统一（observation_helper 共享模块）
- Loop 侧 Observation Reinjection Hardening（preview 优先回灌）
- CLI 与 Run Artifact 可见性补强（截断提示 + artifact 路径）
- 测试基线从 858 passed 提升到 943 passed

### Phase 2.3A：Backup / Rollback / Edit History

- edit_history_store：最小持久化存储
- write/edit 前自动备份，成功后记录历史
- CLI 命令：/history 和 /rollback latest
- 支持 created（删除文件）和 modified（恢复备份）两种回退
- 测试基线从 943 passed 提升到 971 passed

### Phase 2.3B：Session 级 Permission Policy

- session_policy.py：内存态 store，支持 allow-once / allow-session
- bash 按精确 command 匹配，write/edit 按规范化路径匹配
- CLI 确认支持 y/a/n/Enter
- 测试基线从 971 passed 提升到 994 passed

### Phase 2.3C：真实远程 LLM Smoke

- 环境门控：RUN_REAL_LLM_SMOKE=1，MIMO_API_KEY 缺失时自动 skip
- client smoke：验证配置读取、client 初始化、远程 API 可达
- agent loop smoke：验证默认装配路径、tool use -> observation -> final answer
- 测试基线从 994 passed 提升到 997 passed

### Phase 3.1：Session / Workspace 增强

- Task 1：session 可持久化、可恢复
- Task 4：autosave 进入默认使用体验
- Task 2：/session、/sessions、/inspect CLI 命令
- Task 3：freshness-aware resume
- 测试基线从 997 passed 提升到 1061 passed

### Phase 3.2A：Evaluation Baseline 固化

- 统一 baseline runner：scripts/run_phase32_baseline.py
- Memory baseline：memory_on vs memory_off
- Recovery baseline：rollback / backup / history
- Permission baseline：ASK / session allow / deny preservation
- 测试基线从 1061 passed 提升到 1072 passed

### Phase 3.2E：Benchmark Hardening - Realistic Memory Evaluation

- 去 mock 化：MemoryExperiment 默认走 ScriptedModelClient + 真实 AgentLoop
- 敏感任务重构：新增 3 个 memory_sensitive 任务，memory_on/off 产生真实差异
- 指标体系调整：主效果指标切到效率指标（avg_tool_calls, target_reread_rate 等）
- 专用 memory eval runner：scripts/run_phase32_memory_eval.py
- 测试基线从 1096 passed 提升到 1101 passed
- 关键结果：FakeModelClient 下首次观察到 memory_on vs memory_off 差异（avg_tool_calls 10x, correct_rate +7pp）

## 必须做

1. 修复 rollback 后缓存同步问题（2.3A follow-up）

## 应该做

1. Phase 3.2C：Reflection（现在有了可信基线，更值得做）
2. Phase 3.2D：Hermes Curator
3. backup 文件清理策略
4. 多版本回滚（当前只支持最近一次）

## 可以暂缓

1. durable memory 的进一步产品化
2. 更复杂的 context routing

## 不建议现在做

1. MCP
2. WebUI
3. 长期记忆检索产品化
4. 复杂多 agent 并行
5. Nanobot / Hermes 式大迁移
