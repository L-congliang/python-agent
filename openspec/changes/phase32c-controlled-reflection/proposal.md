## Why

Phase 3.2E 已建立可信的 memory benchmark 基线，证明 memory_on 比 memory_off 在效率和正确率上有显著差异。但当前 agent 仍会在部分 L3/L4 任务上答错，也可能出现"有 memory 但第一次执行没用好"的情况。

核心问题：
- agent 第一次执行失败后，能不能基于已有轨迹做一次有边界的反思？
- 这次反思能不能减少不必要 reread / 提升高依赖任务成功率？
- 这件事能不能被 benchmark 量化，而不是只说"感觉更聪明了"？

### 借鉴来源

- **Reflexion**（Shinn et al. 2023）：verbal reinforcement，用语言反思改进策略
- **Self-Refine**（Madaan et al. 2023）：生成 → 反思 → 精炼的迭代循环
- 但本项目只取其核心思想的最小可用版本：one-shot reflection + one retry

### 不做的事

- 不做 Hermes 那种 broad self-improving loop
- 不做长期自进化 / 自动改 prompt / 自动长程技能生长
- 不做 agent 自主无限 retry / 递归 reflection
- 不做 skill library / curator / 自动 memory rewrite
- 不做 MCP / WebUI / 多 agent
- Phase 1 不改 AgentLoop 核心代码

## What Changes

### 新增能力

- `controlled-reflection`: 受控单次自纠正机制
  - ReflectionConfig（独立配置，不污染 LoopConfig）
  - ReflectionPolicy（触发条件判定）
  - ReflectionBuilder（构造预算受控的反思 prompt）
  - Benchmark 集成（before/after 对比）

### 核心交付

1. **Reflection Contract** — 触发条件、配置、数据结构独立稳定
2. **Reflection Builder** — 预算受控的反思 prompt 构造
3. **Benchmark Integration** — memory_on vs memory_on+reflection 对比
4. **Phase 2 仅在 Phase 1 证明有效后启动** — Loop 接入 + 文档固化

### 一句话边界

3.2C Phase 1 做 bounded one-shot self-correction 的 benchmark 验证，不做 loop 改造，不做自进化。

## Capabilities

### New Capabilities

- `controlled-reflection`:
  - ReflectionConfig dataclass（独立于 LoopConfig）
  - ReflectionPolicy（触发条件：incorrect / reread / high tool_calls）
  - ReflectionBuilder（预算受控的反思 prompt 构造）
  - Benchmark 集成（reflection_trigger_rate, reflection_retry_success_rate 等）

### Modified Capabilities

- `memory-evaluation`: MemoryExperiment 支持 reflection retry 路径

## Impact

- **代码结构**：
  - 新增 `src/agent/reflection/` 模块（types.py, policy.py, builder.py）
- **现有代码**：
  - `src/agent/evaluation/memory_experiment.py` — 新增 reflection retry 逻辑
  - `scripts/run_phase32_memory_eval.py` — 支持 `--with-reflection` 选项
- **测试**：
  - 新增 `tests/test_reflection_policy.py`
  - 新增 `tests/test_reflection_builder.py`
  - 新增 `tests/test_reflection_eval_runner.py`
- **依赖**：无新增外部依赖
- **目录结构**：新增 `src/agent/reflection/` 模块目录

## 约束

- **Phase 1 不改 AgentLoop** — reflection 只在 MemoryExperiment 层实现
- **每任务最多 1 次 reflection retry** — 不允许递归反思
- **reflection 输入预算受控** — 不破坏 observation budget
- **默认本地运行不依赖真实 API key** — 用 ScriptedModelClient
- **ScriptedModelClient 用固定 retry script** — 保持 deterministic
- **全量测试必须保持绿色**
