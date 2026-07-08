## Why

Phase 3.2A 建立了 baseline runner，Phase 3.2B 实现了 Memory v2（Cross-Session Retrieval + Layered Memory）。但当前评测体系存在**两个根本缺陷**，导致无法回答"Memory v2 到底有没有让 agent 更强"：

### 缺陷 1：默认 baseline 走 mock 路径

`scripts/run_phase32_baseline.py` 调用 `MemoryExperiment(use_real_model=False)`，而 `use_real_model=False` 走 `_run_mock_task()`，直接返回：
- `correct=True`
- `tool_calls=2`
- `duration=0.5`
- `memory_hits` 按配置机械赋值

**连真实 agent 行为都没在测。** 任何基于此的"结论"都是 mock 产物。

代码证据：
- `scripts/run_phase32_baseline.py:42` — 调用 `MemoryExperiment(use_real_model=False)`
- `src/agent/evaluation/memory_experiment.py:1050` — `use_real_model=False` 走 `_run_mock_task()`
- `src/agent/evaluation/memory_experiment.py:1070` — `_run_mock_task()` 直接返回常量

### 缺陷 2：setup_turns 信息留在同一段消息上下文里

`memory_experiment.py:1088` 里 setup_turns 先 `loop.run(setup_prompt)`，然后只 `clear_tool_history()`（line 1099），**没有清空消息历史**。主任务时模型仍能从同一个对话上下文里拿到 setup 信息。

**memory 不构成必要条件。** 模型从 messages 里回看就能找到答案，correct_rate 天然顶满。

### 当前量化现状

当前正确率饱和，部分诊断指标出现反直觉现象（如 memory_hit_rate 在 memory_off 时反而更高），需要重新校准评测体系。详见历史诊断数据：`docs/test-reports/P2-memory-v2-formal-summary.md`、`docs/test-reports/smoke-v4.md`。

### 借鉴来源

- **Hermes**：评测必须"诚实"，不能用 mock 产物冒充真实结论
- **Nanobot**：评测基础设施要能支撑前后对比

### 不做的事

- 不做 Phase 3.2C Reflection（需要先有可信基线）
- 不做 Hermes Curator
- 不做 recovery / permission 的完整真实实验接入
- 不做 MCP / WebUI / multi-agent
- 不做 embedding / vector DB / RAG
- 不做大规模真实远程 benchmark
- real-model selective eval 如时间紧可延后

## What Changes

### 改造能力

- `memory-evaluation`: 从"链路存在证明"升级为"能区分 Memory v2 是否真的有用"的现实评测

### 核心交付

1. **baseline 文档口径清理** — 消除认知债务，文档与真实产物一致
2. **MemoryExperiment 去 mock 化** — 默认走 FakeModelClient + 真实 loop
3. **敏感任务重构** — 设计让 memory 真正必要或无 memory 路径明显更昂贵的任务
4. **专用 memory eval runner** — 适合 before/after 对比的 runner + 报告
5. **指标体系调整** — 主效果指标从 correct_rate 切换到效率指标
6. **文档固化** — 诚实说明"提升了什么 / 还没提升什么"

### 一句话边界

3.2E 做 benchmark hardening，不做新能力堆叠。

## Capabilities

### Modified Capabilities

- `memory-evaluation`:
  - 去 mock 化：默认走 FakeModelClient + 真实 AgentLoop
  - 任务重构：新增 cross-session recall、episodic_notes 组合等敏感任务
  - 指标调整：avg_tool_calls / target_reread_rate / answer_without_reread_rate 升级为主效果指标
  - memory_hit_rate 降级为诊断指标
  - memory_irrelevant 纳入正式报告

### New Capabilities

- `memory-eval-runner`: 专用 memory 评测 runner
  - 输出 memory_on / memory_off / memory_irrelevant 三组对比
  - 报告区分主效果指标和诊断指标
  - 适合 before/after 对比

## Impact

- **代码结构**：
  - 改造 `src/agent/evaluation/memory_experiment.py`（执行路径 + 任务集）
  - 新增 `scripts/run_phase32_memory_eval.py`
  - 可选新增 `scripts/run_real_memory_eval.py`
- **现有代码**：
  - `scripts/run_phase32_baseline.py` — 保持不变，继续作为宽快照入口
- **测试**：
  - 改造 `tests/test_memory_experiment.py`
  - 改造 `tests/test_memory_cross_session.py`
  - 可新增 `tests/test_memory_eval_runner.py`
  - 可新增 `tests/test_real_memory_eval_smoke.py`
- **文档**：
  - 更新 `docs/agent-improvement/13-phase3.2-eval-baseline.md`
  - 更新 `docs/agent-improvement/14-phase3.2b-memory-v2.md`
  - 新增 `docs/agent-improvement/15-phase3.2e-benchmark-hardening.md`
- **依赖**：无新增外部依赖
- **目录结构**：无新增运行时目录

## 约束

- **默认本地运行不依赖真实 API key** — 用 FakeModelClient 驱动真实 loop
- **不改 AgentLoop 核心逻辑** — 只改 MemoryExperiment 的调用方式
- **不改 Memory v2 架构** — 只改评测层
- **real-model selective eval 可延后** — 但文档要标注为"后续建议项"
- **全量测试必须保持绿色** — 改造过程中不能破坏现有测试
