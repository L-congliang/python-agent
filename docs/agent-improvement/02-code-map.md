# 代码地图

## 1. 默认入口

- `src/agent/main.py`
  - `create_default_registry()`
  - `create_agent_loop()`
  - `create_message_handler()`
  - `create_agent_app()`
  - `main()`

这部分是 Phase 2.1 新增的装配切分点，也是 smoke test 的重点。

## 2. 核心调度

- `src/agent/core/loop.py`
  - 多轮主循环
  - 权限三态
  - workspace guard
  - tool execution
  - tool result 回注

## 3. 工具层

- `src/agent/tools/registry.py`
  - `register_base_tools()`
  - `validate_and_execute()`
- `src/agent/tools/file_read.py`
- `src/agent/tools/file_write.py`
- `src/agent/tools/file_edit.py`
- `src/agent/tools/bash.py`
- `src/agent/tools/grep.py`
- `src/agent/tools/glob.py`
- `src/agent/tools/observation_helper.py`（Phase 2.2 新增）
  - `truncate_output()` - 统一截断逻辑
  - `build_observation()` - 构建 observation 双层契约

## 4. 权限层

- `src/agent/permissions/checker.py`
  - `DEFAULT`
  - `PLAN`

- `src/agent/core/types.py`
  - `PermissionDecision`
  - `PermissionRequest`
  - `PermissionConfirmationOutcome`

## 5. CLI 层

- `src/agent/cli/app.py`
  - 命令处理
  - 工具结果渲染
  - `confirm_permission()`
  - Windows 非 UTF-8 fallback

## 6. 演示最相关测试

- `tests/test_main_smoke.py`
  - 默认入口装配 smoke test
- `tests/test_e2e_agent_workflow.py`
  - 任务级 e2e
- `tests/test_agent_loop.py`
  - 权限和 loop 行为
- `tests/test_cli.py`
  - CLI 交互与确认
- `tests/test_observation_contract.py`（Phase 2.2 新增）
  - ObservationMetadata 和 ToolResult 测试
- `tests/test_loop_compaction.py`（Phase 2.2 新增）
  - Observation Reinjection 测试
- `tests/test_observation_truncation.py`（Phase 2.2 新增）
  - 截断逻辑和 artifact 化测试

## 7. 面试时最该看哪些代码

- `README.md`
- `src/agent/main.py`
- `src/agent/core/loop.py`
- `src/agent/tools/registry.py`
- `src/agent/permissions/checker.py`
- `src/agent/tools/file_edit.py`
- `src/agent/tools/observation_helper.py`（Phase 2.2 新增，展示上下文压缩设计）
- `tests/test_main_smoke.py`
- `tests/test_e2e_agent_workflow.py`
