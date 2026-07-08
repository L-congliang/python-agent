# 测试记录

更新时间：2026-07-06

## 本轮实际执行命令

```powershell
$env:UV_CACHE_DIR=(Join-Path (Resolve-Path '.').Path '.uv-cache')
uv run pytest tests/test_main_smoke.py -q
uv run pytest tests/test_e2e_agent_workflow.py -q
uv run pytest tests/test_agent_loop.py -q
uv run pytest tests/test_cli.py -q
uv run pytest tests -q
```

## 结果

- `uv run pytest tests/test_main_smoke.py -q`
  - `8 passed`
- `uv run pytest tests/test_e2e_agent_workflow.py -q`
  - `3 passed`
- `uv run pytest tests/test_agent_loop.py -q`
  - `32 passed`
- `uv run pytest tests/test_cli.py -q`
  - `47 passed`
- `uv run pytest tests -q`
  - `858 passed, 3 skipped`

## 本轮新增覆盖点

- `tests/test_main_smoke.py`
  - 默认 registry 装配
  - 默认 loop 装配
  - CLI confirmation handler 挂载
  - `/reset`
  - `/compact`
  - 非 UTF-8 fallback
  - 缺少 API key 时主入口退出行为
  - 直接调用 `main()` 的默认入口装配 smoke
- `tests/test_e2e_agent_workflow.py`
  - 任务级 e2e

## 当前仍未覆盖的点

- 真正远程 LLM 驱动的 CLI smoke
- 完整 rollback 流程
- session 级 permission policy

---

## Phase 2.2 测试记录

更新时间：2026-07-06

### 本轮实际执行命令

```bash
uv run pytest tests/test_observation_contract.py -q
uv run pytest tests/test_loop_compaction.py -q
uv run pytest tests/test_observation_truncation.py -q
uv run pytest tests/test_cli_observation.py -q
uv run pytest tests -q
```

### 结果

- `uv run pytest tests/test_observation_contract.py -q`
  - `12 passed`
- `uv run pytest tests/test_loop_compaction.py -q`
  - `16 passed`
- `uv run pytest tests/test_observation_truncation.py -q`
  - `17 passed`
- `uv run pytest tests/test_cli_observation.py -q`
  - `13 passed`
- `uv run pytest tests -q`
  - `916 passed, 3 skipped`

### 本轮新增覆盖点

- `tests/test_observation_contract.py`
  - ObservationMetadata 默认值
  - ToolResult 向后兼容
  - ToolResult 带 observation
  - 边界情况（Unicode、大输出）
- `tests/test_loop_compaction.py`
  - `_resolve_observation_content` 单元测试
  - `_handle_tool_results` 集成测试
  - 混合场景（有/无 observation）
  - 边界情况
- `tests/test_observation_truncation.py`
  - `truncate_output` 函数测试（tail/head 策略）
  - `build_observation` 函数测试
  - artifact 保存逻辑
  - 边界情况（大输出、Unicode）
- `tests/test_cli_observation.py`
  - `show_tool_result` 支持 observation
  - `_handle_event` 处理 tool_result 事件
  - 截断提示显示逻辑
  - 边界情况

### 测试基线对比

| 阶段 | 测试数 | 通过 | 跳过 | 失败 |
|------|--------|------|------|------|
| Phase 2.1 | 858 | 858 | 3 | 0 |
| Phase 2.2（修复后） | 943 | 943 | 3 | 0 |
| Phase 2.3A | 971 | 971 | 3 | 0 |
| Phase 2.3B | 994 | 994 | 3 | 0 |
| Phase 2.3C | 997 | 997 | 6 | 0 |
| Phase 3.1 Task 1 | 1017 | 1017 | 6 | 0 |
| Phase 3.1 Task 4 | 1033 | 1033 | 6 | 0 |
| Phase 3.1 Task 2 | 1045 | 1045 | 6 | 0 |
| Phase 3.1 Task 3 | 1061 | 1061 | 6 | 0 |
| Phase 3.2A | 1073 | 1073 | 6 | 0 |
| Phase 3.2B | 1096 | 1096 | 6 | 0 |
| Phase 3.2E | 1101 | 1101 | 6 | 0 |
| Phase 3.2C | 1129 | 1129 | 6 | 0 |
| Phase 3.2F | 1132 | 1132 | 6 | 0 |
| **新增** | **+274** | **+274** | **+3** | **0** |

### 测试分类说明

| 类型 | 说明 | 是否依赖真实 API |
|------|------|------------------|
| 单元测试 | 测试单个函数/类 | ❌ |
| 集成测试 | 测试多个模块协作 | ❌ |
| Fake-model e2e | 使用 FakeModelClient 的端到端测试 | ❌ |
| 真实远程 smoke | 验证真实 API 链路没断 | ✅（需 RUN_REAL_LLM_SMOKE=1 + MIMO_API_KEY） |
