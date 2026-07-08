## Context

Phase 3.2E 建立了可信的 memory benchmark 基线。Phase 3.2C 在此基础上引入 bounded one-shot self-correction，先在 benchmark 层验证 reflection 是否有效，再决定是否改 loop。

## Goals / Non-Goals

**Goals (Phase 1):**
- 定义清晰的 Reflection Contract（触发条件、配置、数据结构）
- 实现预算受控的 Reflection Builder
- 在 MemoryExperiment 层实现 one-shot reflection retry
- 用 benchmark 量化 reflection 的收益（before/after 对比）
- 验证 reflection 是否提升 correct_rate / memory_dependent_success_rate

**Goals (Phase 2, 仅在 Phase 1 证明有效后):**
- 将 reflection 接入 AgentLoop
- 真实 agent 的 failure detection（保守 heuristic）
- 文档固化

**Non-Goals:**
- 不做 broad self-improving loop
- 不做递归 reflection / 无限 retry
- 不做自动 memory rewrite / prompt rewrite
- 不做 skill library / curator
- Phase 1 不改 AgentLoop 核心代码

## Decisions

### D1：Reflection 接入位置 — 分阶段

**选择：Phase 1 只在 MemoryExperiment 层实现，不改 AgentLoop。**

```
Phase 1（benchmark 验证）：
  MemoryExperiment._run_scripted_task()
    → first attempt → verifier → 如果失败 →
    → ReflectionBuilder 构造 prompt →
    → second attempt（用 retry script）→ verifier → result

Phase 2（loop 接入，仅在 Phase 1 证明有效后）：
  AgentLoop.run()
    → first attempt → heuristic 检测 →
    → reflection prompt → retry → result
```

**为什么分阶段：**
- benchmark 层有 verifier，可以准确判断"第一次失败"
- 真实 agent 没有 verifier，failure detection 更复杂
- 先在安全的实验层验证价值，再决定是否改核心代码
- 如果 benchmark 显示 reflection 无用，就不需要改 loop

### D2：ReflectionConfig 放置 — 独立 dataclass

**选择：独立的 ReflectionConfig dataclass，不塞进 LoopConfig。**

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

**为什么独立：**
- Phase 1 reflection 是评测层概念，不是 loop 层概念
- 独立 dataclass 最灵活，benchmark 和未来 loop 都能用
- 避免过早污染 LoopConfig 接口

### D3：ScriptedModelClient 的 second attempt — 固定 retry script

**选择：每个 task 可提供固定的 retry_script，不搞动态生成。**

```python
MemoryTask:
    first_attempt_script: list[...]  # 第一次尝试的行为
    retry_script: list[...]          # reflection 后的重试行为
```

**为什么固定 script：**
- benchmark 目标是验证 reflection 机制和收益，不是模拟模型自省
- 动态 script generation 会让评测失去可控性
- 固定 script 仍然可以展示"不同行为路径 → 不同结果"

**retry_script 的设计思路：**
- 对于"第一次读错文件"的 task：retry_script 跳过 reread，直接回答
- 对于"第一次没用 memory"的 task：retry_script 从 memory 回答
- 对于"第一次答错"的 task：retry_script 读取正确文件后回答

### D4：触发条件 — 三个明确触发器

**选择：三个触发条件，满足任一即触发 reflection。**

| 触发条件 | 判定方式 | 说明 |
|----------|---------|------|
| incorrect | verifier 返回 False | 第一次答错 |
| read_target_after_setup | `_check_target_reread()` 返回 True | 不必要 reread |
| high tool_calls | tool_calls > threshold | 效率过低 |

**为什么这三个：**
- incorrect：最直接的失败信号
- read_target_after_setup：memory 应该避免的低效行为
- high tool_calls：兜底，防止模型走弯路

**不做的事：**
- 不用 LLM 自评作为触发器（Phase 1 有 verifier，不需要）
- 不做 recursive reflection（每任务最多 1 次）

### D5：Reflection 输入 — 预算受控

**选择：ReflectionBuilder 构造预算受控的反思 prompt，不灌全量上下文。**

反思输入包含：
- 原任务 prompt
- 第一次回答结果摘要（正确/错误 + 原因）
- tool trajectory 摘要（哪些工具被调用、是否 reread）
- memory_hit 状态
- verifier failure signal
- 当前 recall / memory 摘要

反思输出格式（结构化）：
```
failure_reason: ...
likely_mistake: ...
retry_strategy: ...
should_reread_target: yes/no
minimal_next_action: ...
```

**为什么预算受控：**
- 不破坏 Phase 3.2E 的 observation budget 设计
- reflection prompt 应该是"反思摘要"，不是"再来一遍全量上下文"
- 控制 token 开销

### D6：Benchmark 集成 — 增强现有 runner

**选择：增强 `run_phase32_memory_eval.py`，支持 `--with-reflection`，不新建 runner。**

输出对比：
- memory_on（baseline）
- memory_on_reflection（reflection enabled）
- memory_off（对照组）

新增指标：
- reflection_trigger_rate：触发 reflection 的任务比例
- reflection_retry_success_rate：reflection 后重试成功的比例
- reflection_avg_extra_tool_calls：reflection 引入的额外 tool calls
- first_to_second_correctness_gain：第一次→第二次的正确率提升
- reflection_helped_tasks：reflection 确实帮助了的任务数

**为什么增强现有 runner：**
- 避免维护两个 runner
- 直接对比更清晰
- 复用已有的指标计算逻辑

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|------|------|------|
| Reflection 在 benchmark 下无提升 | Phase 2 不启动 | 诚实写清结论，不强行包装 |
| 固定 retry script 太理想化 | 可能高估 reflection 收益 | 文档标注"scripted benchmark"的局限 |
| reflection prompt 构造不当 | 反思无效或误导 | 先在 2-3 个 task 上手动验证 |
| 指标解读偏差 | 把"reflection 触发率高"误读为"agent 很弱" | 报告区分"reflection 帮助了"和"reflection 没帮助" |
