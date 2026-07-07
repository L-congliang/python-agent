# 下一步路线

## 已完成

### Phase 2.2：Observation / Context Compression Hardening

- 统一 Observation Budget 契约（ToolResult + ObservationMetadata）
- 工具层输出截断与 Artifact 化统一（observation_helper 共享模块）
- Loop 侧 Observation Reinjection Hardening（preview 优先回灌）
- CLI 与 Run Artifact 可见性补强（截断提示 + artifact 路径）
- 测试基线从 858 passed 提升到 916 passed

## 必须做

1. 继续补 integration / smoke coverage
   - 尤其是默认 CLI 运行路径

2. 把 demo 路径做得更顺手
   - 最好准备一套固定的 demo workspace / 录屏脚本

3. 明确 `file_edit` 后续恢复方案
   - 是临时 backup
   - 还是更正式的 rollback artifact

## 应该做

1. Backup / Rollback / Edit History（现在有了 artifact 基础，更顺手）
2. session 级 permission policy
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
