## Why

Phase 3.2C Phase 1 已证明 policy-triggered scripted retry with reflection prompt 有局部效率收益。但最后一个边界还在：

**当前 benchmark 是 scripted benchmark，不是 prompt-sensitive benchmark。**

ScriptedModelClient 按固定 rounds 执行，不根据 reflection prompt 内容分支。所以当前收益可能来自"第二次重试"机制本身，而非 reflection 内容。

本阶段目标：让 retry 行为真正对 reflection prompt 内容敏感，把因果链从"有 retry 就有效"推进到"reflection 内容本身影响 retry 决策"。

### 不做的事

- 不改 AgentLoop
- 不改 first attempt 行为（保持 baseline 干净）
- 不做大规模 real-model benchmark
- 不做 recursive reflection
- 不做自动 memory rewrite

## What Changes

### 新增能力

- `PromptAwareScriptedModelClient`：根据 reflection prompt 中的 `retry_strategy` 字段选择不同 retry branch
- `ReflectionPlan`：ReflectionBuilder 的结构化输出（prompt + retry_strategy + should_reread_target）
- `retry_branches`：MemoryTask 的多路径 retry 定义
- 三组对比 benchmark：baseline / scripted retry / prompt-sensitive retry

### 一句话边界

3.2F 做 prompt-sensitive scripted benchmark hardening，不改 loop，不碰 first attempt。

## Capabilities

### New Capabilities

- `prompt-sensitive-benchmark`:
  - PromptAwareScriptedModelClient（根据 prompt 内容选 branch）
  - ReflectionPlan dataclass（结构化 reflection 输出）
  - retry_branches（task 定义所有合法 retry 路径）
  - 三组对比 benchmark

### Modified Capabilities

- `controlled-reflection`: ReflectionBuilder 输出从 str 改为 ReflectionPlan
- `memory-evaluation`: MemoryTask 新增 retry_branches 字段

## Impact

- **代码结构**：
  - `src/agent/evaluation/fake_client.py` — 新增 PromptAwareScriptedModelClient
  - `src/agent/reflection/builder.py` — 输出改为 ReflectionPlan
  - `src/agent/reflection/types.py` — 新增 ReflectionPlan
  - `src/agent/evaluation/memory_experiment.py` — MemoryTask 新增 retry_branches，run 支持三组对比
- **测试**：
  - `tests/test_fake_client.py` — 测试 PromptAwareScriptedModelClient
  - `tests/test_reflection_builder.py` — 测试 ReflectionPlan 输出
  - `tests/test_reflection_eval_runner.py` — 测试三组对比
- **依赖**：无新增外部依赖

## 约束

- **first attempt 不变** — 保持 baseline deterministic 行为
- **只在 reflection retry 场景用 prompt-sensitive client**
- **三组对比优先在 reflection-sensitive 子集上跑**（不全量 27 任务）
- **必须有 default_retry_branch fallback**
- **默认本地运行不依赖真实 API key**
