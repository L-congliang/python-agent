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

### Phase 2.3A Follow-up

- **rollback 后 file_read_state / loop 内缓存未同步**
  - 影响：同一 session 内回退后再读文件，可能看到旧内容
  - 原因：rollback 在 store 层面，不经过 context
  - 优先级：P1（真实 agent 行为风险）

## 必须做

1. 修复 rollback 后缓存同步问题（2.3A follow-up）
2. Session 级 permission policy（2.3B）
3. 真实远程 LLM 回归链路（2.3C）

## 应该做

1. backup 文件清理策略
2. 多版本回滚（当前只支持最近一次）
3. 更清晰的 run artifact 展示

## 可以暂缓

1. durable memory 的进一步产品化
2. 更复杂的 context routing

## 不建议现在做

1. MCP
2. WebUI
3. 长期记忆检索产品化
4. 复杂多 agent 并行
5. Nanobot / Hermes 式大迁移
