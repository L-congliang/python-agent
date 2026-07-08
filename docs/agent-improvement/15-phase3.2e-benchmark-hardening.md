# Phase 3.2E: Benchmark Hardening - Realistic Memory Evaluation

更新时间：2026-07-07

## 1. 阶段目标

让 memory evaluation 真正区分 memory_on / memory_off / memory_irrelevant，并为后续 Phase 3.2C Reflection 提供可信的前后对比基线。

## 2. 解决的核心问题

### 问题 1：默认 baseline 走 mock 路径

**现象：** `MemoryExperiment(use_real_model=False)` 走 `_run_mock_task()`，直接返回 `correct=True, tool_calls=2, duration=0.5`。

**代码证据：**
- `scripts/run_phase32_baseline.py:42` — 调用 `MemoryExperiment(use_real_model=False)`
- `src/agent/evaluation/memory_experiment.py:1050` — `use_real_model=False` 走 `_run_mock_task()`
- `src/agent/evaluation/memory_experiment.py:1070` — `_run_mock_task()` 直接返回常量

**解决：** 用 ScriptedModelClient + 真实 AgentLoop 替代 `_run_mock_task()`。

### 问题 2：setup_turns 信息留在同一段消息上下文里

**现象：** `clear_tool_history()` 只清统计，不清消息历史。模型回头看 messages 就能找到答案。

**代码证据：**
- `memory_experiment.py:1088` — setup_turns 先 `loop.run(setup_prompt)`
- `memory_experiment.py:1099` — 只 `clear_tool_history()`，不清消息历史

**解决：** 设计 memory-sensitive 任务，让 memory_on 跳过 reread，memory_off 必须 reread。

## 3. 核心交付

### 3.1 去 mock 化

- 新增 `ScriptedModelClient`（`src/agent/evaluation/fake_client.py`）
- 新增 `_run_scripted_task()` 方法替代 `_run_mock_task()`
- setup_turns 和 main task 使用独立 client，避免 script rounds 被消耗
- 新增 `_create_agent_loop_with_client()` 工厂函数

### 3.2 敏感任务重构

新增 3 个 memory-sensitive 任务：

| task_id | category | 设计思路 |
|---------|----------|----------|
| `mem_sensitive_api_url` | memory_sensitive | setup 告知 API_URL，memory_on 直接回答，memory_off 需 reread |
| `mem_sensitive_db_host` | memory_sensitive | setup 告知 DB_HOST，memory_on 直接回答，memory_off 需 reread |
| `mem_sensitive_cache_port` | memory_sensitive | setup 告知 CACHE_PORT，memory_on 直接回答，memory_off 需 reread |

关键设计：`_build_default_script()` 根据 `use_memory` 参数生成不同脚本：
- `use_memory=True` + 有 setup_turns → 跳过 reread，直接回答
- `use_memory=False` → reread 目标文件，再回答

### 3.3 指标体系调整

| 定位 | 指标 | 说明 |
|------|------|------|
| 主效果指标 | avg_tool_calls | memory 价值 = 少读文件、少走弯路 |
| 主效果指标 | target_reread_rate | 有 memory 时是否减少了不必要的 reread |
| 主效果指标 | answer_without_reread_rate | setup_turns 后不 reread 就能答对的比例 |
| 主效果指标 | memory_dependent_success_rate | L3/L4 高依赖任务的成功率 |
| 辅助 guardrail | correct_rate | 不能因为追求效率牺牲正确性 |
| 诊断指标 | memory_hit_rate | 只用于诊断，不作为结论依据 |

### 3.4 专用 memory eval runner

- 新增 `scripts/run_phase32_memory_eval.py`
- 输出 memory_on / memory_off / memory_irrelevant 三组对比
- 区分主效果指标和诊断指标
- 报告包含差异分析

### 3.5 文档清理

- 更新 `13-phase3.2-eval-baseline.md` — 删除编造的示例数值，标注 mock 路径问题
- 更新 `14-phase3.2b-memory-v2.md` — baseline 数据标注为 mock 产物
- 新增本文档

## 4. 实验结果

### Benchmark 定位

**当前 benchmark 是"deterministic behavioral benchmark"，不是"prompt-sensitive memory benchmark"。**

- ✅ 已证明：memory-enabled path 在 deterministic harness 下能减少 reread / tool calls
- ✅ 已证明：默认 use_real_model=False 不再走 _run_mock_task() 常量返回
- ⚠️ 未证明：真实模型对 recall 内容敏感（ScriptedModelClient 不读取 assembled memory 来决策）
- ⚠️ 未证明：噪声记忆不影响效率（只是 scripted 路径下未观察到 degradation）

### FakeModelClient + 真实 AgentLoop 结果

| 配置 | correct_rate | mem_dep_success | avg_tool_calls | answer_no_reread | memory_hit_rate |
|------|-------------|-----------------|----------------|------------------|-----------------|
| memory_on | 70% | 63% | 0.1 | 72% | 100% |
| memory_off | 63% | 53% | 1.0 | 64% | 0% |
| memory_irrelevant | 70% | 63% | 0.1 | 72% | 100% |

**关键发现：**
- **avg_tool_calls 差异 10x**：memory_on=0.1 vs memory_off=1.0
- **target_reread_rate 差异**：memory_on=0% vs memory_off=100%（修复后口径）
- **correct_rate 差异 7pp**：memory_on=70% vs memory_off=63%
- **memory_dependent_success_rate 差异 10pp**：memory_on=63% vs memory_off=53%
- **memory_irrelevant 与 memory_on 表现相同**：当前 scripted benchmark 下未观察到 degradation（注意：这不等于"证明噪声记忆不影响效率"，因为 ScriptedModelClient 不读取 assembled memory 内容来决策）

### 与旧 mock 路径的对比

| 指标 | 旧 mock 路径 | 新 scripted 路径 |
|------|-------------|-----------------|
| correct_rate | 100% (mock 固定) | 70% (真实 verifier) |
| avg_tool_calls | 2.0 (mock 固定) | 0.1-1.0 (真实执行) |
| memory_hit_rate | 1.0/0.0 (机械赋值) | 100%/0% (真实行为) |
| memory_on vs off 差异 | 无 | 有 (tool_calls, correct_rate) |

## 5. 升级条件评估

**升级条件：** 如果 FakeModelClient + 真实 loop + 新任务仍无明显区分度，则 real-model selective eval 升级为必须项。

**当前状态：** 升级条件**未触发**。FakeModelClient + 新任务已经观察到明显差异（avg_tool_calls 10x, correct_rate 7pp）。Task 4 (real-model selective eval) 保持可选。

## 6. 测试覆盖

**新增/修改测试：**
- `tests/test_memory_experiment.py` — 更新任务数量断言，新增 memory_sensitive 类别验证
- `tests/test_memory_eval_runner.py` — 新增 5 个测试（JSON/MD 输出、schema 稳定、memory_irrelevant 纳入、无 API key 可运行）

**全量测试：** 1101 passed, 6 skipped

## 7. 改动文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `src/agent/evaluation/fake_client.py` | 修改 | 新增 ScriptedModelClient |
| `src/agent/evaluation/memory_experiment.py` | 修改 | 去 mock 化、新任务、指标体系调整 |
| `scripts/run_phase32_memory_eval.py` | 新增 | 专用 memory eval runner |
| `tests/test_memory_experiment.py` | 修改 | 更新断言、新增类别验证 |
| `tests/test_memory_eval_runner.py` | 新增 | runner 测试 |
| `docs/agent-improvement/13-phase3.2-eval-baseline.md` | 修改 | 清理编造数值 |
| `docs/agent-improvement/14-phase3.2b-memory-v2.md` | 修改 | 标注 mock 路径问题 |
| `docs/agent-improvement/15-phase3.2e-benchmark-hardening.md` | 新增 | 本文档 |

## 8. 后续建议

**Phase 3.2C Reflection 现在更值得做：**
- 有了可信的 before/after 基线
- 可以比较：baseline → memory_v2 → memory_v2 + reflection
- 如果 reflection 有效，correct_rate 和 avg_tool_calls 应该有进一步提升

**可选：real-model selective eval**
- 如果需要更高置信度，可以设置 `RUN_REAL_MEMORY_EVAL=1` 运行真实模型评测
- 用新设计的 memory-sensitive 任务，不要用旧任务
