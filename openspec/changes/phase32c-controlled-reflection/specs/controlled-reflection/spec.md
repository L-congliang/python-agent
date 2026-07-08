## Overview

Phase 3.2C: Controlled Reflection - Bounded Self-Correction

在 MemoryExperiment 层实现 one-shot reflection retry：第一次执行失败后，基于执行轨迹构造预算受控的反思 prompt，触发一次重试，用 benchmark 量化 reflection 的收益。

**定位：** benchmark-first 的受控纠错机制，不是自进化系统。

## Core Concepts

### ReflectionConfig

独立于 LoopConfig 的配置 dataclass，控制 reflection 行为。

```python
@dataclass
class ReflectionConfig:
    enabled: bool = False
    max_reflections_per_task: int = 1
    only_on_failure: bool = True
    enable_on_reread: bool = True
    enable_on_high_tool_calls: bool = True
    tool_call_threshold: int = 5
    reflection_max_tokens: int = 1024
```

### ReflectionPolicy

判定是否触发 reflection 的策略类。三个触发条件：

| 触发条件 | 判定方式 | 说明 |
|----------|---------|------|
| incorrect | verifier 返回 False | 第一次答错 |
| read_target_after_setup | `_check_target_reread()` 返回 True | 不必要 reread |
| high tool_calls | tool_calls > threshold | 效率过低 |

满足任一条件即触发，每任务最多触发 1 次。

### ReflectionBuilder

构造预算受控的反思 prompt。输入是 ReflectionSummary（执行轨迹摘要），输出是结构化反思文本。

反思输入包含：
- 原任务 prompt
- 第一次回答结果摘要
- tool trajectory 摘要
- memory_hit 状态
- verifier failure signal

反思输出格式（结构化）：
```
failure_reason: ...
likely_mistake: ...
retry_strategy: ...
should_reread_target: yes/no
minimal_next_action: ...
```

### Retry Script

每个 MemoryTask 可提供固定的 `retry_script`，定义 reflection 后的重试行为。ScriptedModelClient 用这个 script 执行第二次尝试，保持 deterministic。

## Data Flow

```
MemoryExperiment._run_scripted_task(config, task)
  ↓
First attempt（用 task 的 first_attempt_script 或默认 script）
  ↓
Verifier 判定结果
  ↓
ReflectionPolicy.should_reflect(task, first_result)
  ↓
如果 should_reflect=True 且 task 有 retry_script:
  ↓
ReflectionBuilder.build(summary) → reflection prompt
  ↓
Second attempt（用 task 的 retry_script）
  ↓
Verifier 判定第二次结果
  ↓
返回结果（包含 reflection_triggered, first_attempt_correct 等元数据）
```

## Integration Points

### 与 MemoryExperiment 集成

- `src/agent/evaluation/memory_experiment.py` — `_run_scripted_task` 新增 reflection retry 路径
- 不改 `_run_real_task`（Phase 1 只做 scripted path）

### 与 Benchmark Runner 集成

- `scripts/run_phase32_memory_eval.py` — 支持 `--with-reflection` 选项
- 输出 baseline vs reflection 并列对比

### 不集成的组件（Phase 1）

- `src/agent/core/loop.py` — 不改（Phase 2 再考虑）
- CLI — 不新增命令（Phase 1 是 benchmark 层概念）

## Testing Strategy

### test_reflection_policy.py

- incorrect 时触发
- reread 时触发
- tool_calls 超阈值时触发
- 不满足条件时不触发
- disabled 时完全不触发

### test_reflection_builder.py

- reflection prompt 不为空
- 输入包含 failure / tool summary / memory summary
- 输入长度受控
- 缺少某些字段时能降级工作

### test_reflection_eval_runner.py

- runner 输出 reflection 配置结果
- JSON schema 稳定
- markdown 报告出现 reflection 段落
- baseline vs reflection 能并列输出
- 没有真实 API key 也能跑

## Benchmark Metrics

在 Phase 3.2E 基础上新增：

| 指标 | 说明 |
|------|------|
| reflection_trigger_rate | 触发 reflection 的任务比例 |
| reflection_retry_success_rate | reflection 后重试成功的比例 |
| reflection_avg_extra_tool_calls | reflection 引入的额外 tool calls |
| first_to_second_correctness_gain | 第一次→第二次的正确率提升 |
| reflection_helped_tasks | reflection 确实帮助了的任务数 |

## Constraints

**做：**
- Bounded one-shot self-correction（每任务最多 1 次）
- Budget-controlled reflection input
- 三个明确触发器（incorrect / reread / high tool_calls）
- Benchmark before/after 对比
- 固定 retry script（deterministic）

**不做：**
- Broad self-improving loop
- 递归 reflection / 无限 retry
- 自动 memory rewrite / prompt rewrite
- 改 AgentLoop（Phase 1）
- LLM 自评作为触发器（Phase 1）
- 自进化 agent

**Phase 2 前置条件：** Phase 1 benchmark 必须证明 reflection 有明确价值，才启动 Phase 2。
