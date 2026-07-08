# Phase 3.2A Evaluation Baseline 固化

更新时间：2026-07-07

## 1. 阶段目标

建立一套轻量、稳定、可复用的 baseline evaluation，让项目后续每次借鉴 Nanobot / Hermes 做改进时，都能回答：
- 改进前是什么水平？
- 改进后哪些指标变好了？
- 提升是能力提升，还是只是多了功能？

## 2. 核心交付

### 已完成
- ✅ 统一 baseline runner：`scripts/run_phase32_baseline.py`
- ✅ 输出格式：`{run_id}.json` + `{run_id}.md`
- ✅ 测试覆盖：`tests/test_evaluation_baseline_runner.py`（11 passed）
- ✅ Schema 稳定：memory/recovery/permission 指标字段已定义
- ⚠️ Memory baseline 默认走 `_run_mock_task()` 路径，不是真实 agent 执行（详见下方说明）

### 未完成
- ⚠️ Recovery baseline：当前返回 placeholder（not_measured），需要接入真实实验
- ⚠️ Permission baseline：当前返回 placeholder（not_measured），需要接入真实实验

## 3. 指标状态

| 类别 | 状态 | 说明 |
|------|------|------|
| Memory | ⚠️ mock 路径 | `MemoryExperiment(use_real_model=False)` 走 `_run_mock_task()`，直接返回常量，不是真实 agent 执行 |
| Recovery | ⚠️ placeholder | 返回 not_measured，需要接入真实实验 |
| Permission | ⚠️ placeholder | 返回 not_measured，需要接入真实实验 |

**⚠️ 关键局限：当前 memory baseline 默认走 `_run_mock_task()` 路径（`memory_experiment.py:1050`），直接返回 `correct=True, tool_calls=2, duration=0.5`。这不是真实 agent 行为，任何基于此的"结论"都是 mock 产物。Phase 3.2E 将解决此问题。**

## 4. 测试覆盖

**新增测试文件：**
- `tests/test_evaluation_baseline_runner.py`（11 passed）

**测试覆盖：**
- runner 能收集 memory/recovery/permission 指标
- runner 调用真实 memory_experiment（不是硬编码）
- recovery/permission 返回 not_measured（placeholder）
- runner 输出 markdown 和 json
- runner 不依赖真实 API
- metrics schema 稳定

## 5. 运行命令

```bash
# 运行 baseline
uv run python scripts/run_phase32_baseline.py

# 指定输出目录
uv run python scripts/run_phase32_baseline.py --output-dir .agent/eval

# 运行测试
uv run pytest tests/test_evaluation_baseline_runner.py -q

# 全量测试
uv run pytest tests -q
```

## 6. 输出示例

### JSON 结构

```json
{
  "run_id": "phase32_baseline_20260707_153340",
  "timestamp": "2026-07-07T15:33:40",
  "memory": {
    "memory_on": {
      "correct_rate": 1.0,
      "memory_hit_rate": 1.0,
      "memory_dependent_success_rate": 1.0,
      "target_reread_rate": 0.0,
      "answer_without_reread_rate": 1.0,
      "avg_tool_calls": 2.0,
      "avg_duration": 0.5
    },
    "memory_off": {
      "correct_rate": 1.0,
      "memory_hit_rate": 0.0,
      "memory_dependent_success_rate": 1.0,
      "target_reread_rate": 0.0,
      "answer_without_reread_rate": 0.0,
      "avg_tool_calls": 2.0,
      "avg_duration": 0.5
    }
  },
  "recovery": {
    "rollback_success_rate": "not_measured",
    "backup_created_rate": "not_measured",
    "history_recorded_rate": "not_measured"
  },
  "permission": {
    "ask_count": "not_measured",
    "session_allow_hit_rate": "not_measured",
    "deny_preserved_rate": "not_measured"
  }
}
```

**⚠️ 当前 baseline 的根本局限：**
- 默认走 `_run_mock_task()` 路径（`memory_experiment.py:1050`），直接返回 `correct=True, tool_calls=2, duration=0.5`
- memory_hits 按配置机械赋值（memory_on=1, memory_off=0），不是真实行为
- **correct_rate 饱和（都是 1.0），无法区分 memory_on / memory_off**
- memory_hit_rate 的差异是 mock 逻辑决定的，不是真实 agent 行为
- 这些数值代表"链路跑通"，不代表"Memory v2 有效"
- Phase 3.2E 将解决此问题：去 mock 化 + 敏感任务重构

### Markdown 结构

```markdown
# Phase 3.2A Baseline Report

**Run ID:** phase32_baseline_20260707_153340
**Timestamp:** 2026-07-07T15:33:40

## Memory Baseline

| Metric | memory_on | memory_off | Delta | 说明 |
|--------|-----------|------------|-------|------|
| correct_rate | 1.0 | 1.0 | 0.0 | 饱和，当前任务集无法区分 |
| memory_hit_rate | 1.0 | 0.0 | +1.0 | mock 逻辑赋值，非真实行为 |
| memory_dependent_success_rate | 1.0 | 1.0 | 0.0 | 饱和 |
| target_reread_rate | 0.0 | 0.0 | 0.0 | mock 路径无真实 tool 行为 |
| avg_tool_calls | 2.0 | 2.0 | 0.0 | mock 固定返回 2 |

## Recovery Baseline

| Metric | Value |
|--------|-------|
| rollback_success_rate | ⚠️ not measured |
| backup_created_rate | ⚠️ not measured |

## Permission Baseline

| Metric | Value |
|--------|-------|
| ask_count | ⚠️ not measured |
| session_allow_hit_rate | ⚠️ not measured |

## Notes

- Memory baseline 默认走 `_run_mock_task()` 路径，不是真实 agent 执行
- mock 路径直接返回 correct=True, tool_calls=2, duration=0.5
- memory_hit_rate 差异来自 mock 逻辑的机械赋值，不是真实行为
- Recovery 和 Permission baselines 是 placeholder（not_measured）
- Phase 3.2E 将去 mock 化并重构敏感任务
```

## 7. Tests vs Evaluation 边界

| 维度 | Tests | Evaluation |
|------|-------|------------|
| 目的 | 证明回归没坏 | 证明改进有收益 |
| 运行 | 默认 pytest | 需要显式运行 |
| 依赖 | 不依赖真实 API | 不依赖真实 API |
| 输出 | pass/fail | 量化指标 |
| 频率 | 每次提交 | 每个阶段 |

## 8. 后续使用

**Phase 3.2B（Memory v2）可以：**
- 对比 memory_on vs memory_v2
- 验证 memory v2 是否提升了 correct_rate

**Phase 3.2C（Reflection）可以：**
- 对比 baseline vs reflection_enabled
- 验证 reflection 是否提升了 memory_dependent_success_rate

**Phase 3.2D（Hermes Curator）可以：**
- 对比 baseline vs curator_enabled
- 验证 curator 是否提升了 answer_without_reread_rate
