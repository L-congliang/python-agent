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
- ✅ Memory baseline 已接入真实实验（FakeModelClient）

### 未完成
- ⚠️ Recovery baseline：当前返回 placeholder（not_measured），需要接入真实实验
- ⚠️ Permission baseline：当前返回 placeholder（not_measured），需要接入真实实验

## 3. 指标状态

| 类别 | 状态 | 说明 |
|------|------|------|
| Memory | ✅ 真实实验 | 调用 MemoryExperiment(use_real_model=False)，使用 FakeModelClient |
| Recovery | ⚠️ placeholder | 返回 not_measured，需要接入真实实验 |
| Permission | ⚠️ placeholder | 返回 not_measured，需要接入真实实验 |

**注意：当前 memory baseline 数据来自 FakeModelClient，不是真实远程模型。**

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
      "correct_rate": 0.85,
      "memory_hit_rate": 0.70,
      "avg_tool_calls": 4.5
    },
    "memory_off": {
      "correct_rate": 0.75,
      "memory_hit_rate": 0.0,
      "avg_tool_calls": 6.2
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

**注意：**
- memory 指标来自 FakeModelClient 实验，不是真实远程模型
- recovery 和 permission 指标是 placeholder（not_measured）
- Phase 3.2B+ 会替换为真实实验数据

### Markdown 结构

```markdown
# Phase 3.2A Baseline Report

**Run ID:** phase32_baseline_20260707_153340
**Timestamp:** 2026-07-07T15:33:40

## Memory Baseline

| Metric | memory_on | memory_off | Delta |
|--------|-----------|------------|-------|
| correct_rate | 0.85 | 0.75 | +0.10 |
| avg_tool_calls | 4.50 | 6.20 | -1.70 |

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

- Memory baseline uses FakeModelClient (no real API required)
- Recovery and Permission baselines are placeholder (not_measured)
- Phase 3.2A goal: establish runner, schema, and output format
- Phase 3.2B+ will replace placeholder with real experiment data
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
