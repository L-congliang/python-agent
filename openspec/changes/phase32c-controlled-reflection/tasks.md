## Phase 3.2C: Controlled Reflection - Bounded Self-Correction

### 执行策略

**Phase 1（benchmark 验证）：** 3 个任务卡
- Task 1: Reflection Contract
- Task 2: Reflection Builder
- Task 3: Benchmark Integration with One-Shot Reflection Retry
- → 跑 benchmark → 评估

**Phase 2（仅在 Phase 1 证明有效后）：** 2 个任务卡
- Task 4: Loop Integration
- Task 5: Docs Hardening

---

### 任务卡 1（Phase 1）：Reflection Contract

**目标：** 定义 reflection 的触发条件、配置、数据结构，使其独立稳定。

**建议新增文件：**
- `src/agent/reflection/__init__.py`
- `src/agent/reflection/types.py`
- `src/agent/reflection/policy.py`

**核心数据结构：**

```python
# types.py

@dataclass
class ReflectionConfig:
    """Reflection 配置（独立于 LoopConfig）"""
    enabled: bool = False
    max_reflections_per_task: int = 1
    only_on_failure: bool = True
    enable_on_reread: bool = True
    enable_on_high_tool_calls: bool = True
    tool_call_threshold: int = 5
    reflection_max_tokens: int = 1024

@dataclass
class ReflectionDecision:
    """是否触发 reflection 的判定结果"""
    should_reflect: bool
    reason: str
    trigger_type: str  # "incorrect" | "reread" | "high_tool_calls" | "none"

@dataclass
class ReflectionSummary:
    """反思输入摘要"""
    task_id: str
    original_prompt: str
    first_attempt_correct: bool
    first_attempt_answer_preview: str
    tool_calls: int
    read_target_after_setup: bool
    memory_hit: int
    failure_reason: str
```

```python
# policy.py

class ReflectionPolicy:
    """判定是否触发 reflection"""
    def __init__(self, config: ReflectionConfig): ...
    def should_reflect(
        self,
        task: MemoryTask,
        first_result: dict[str, Any],
    ) -> ReflectionDecision: ...
```

**测试先写：**
- `tests/test_reflection_policy.py`

**测试覆盖：**
- [ ] incorrect 时触发（first_result.correct=False）
- [ ] reread 时触发（first_result.read_target_after_setup=True）
- [ ] tool_calls 超阈值时触发
- [ ] 不满足条件时不触发
- [ ] 同一任务最多一次（由调用方保证，policy 只做判定）
- [ ] disabled 时完全不触发
- [ ] multiple triggers 时返回第一个匹配的 trigger_type

**验收标准：**
- [ ] ReflectionConfig 独立于 LoopConfig
- [ ] ReflectionPolicy 可单测，不依赖 loop
- [ ] 触发条件清晰、可枚举
- [ ] 不改现有默认行为

---

### 任务卡 2（Phase 1）：Reflection Builder

**目标：** 把反思输入做成预算受控的摘要，不灌全量上下文。

**建议新增文件：**
- `src/agent/reflection/builder.py`

**Builder 输入：**
- `ReflectionSummary`（来自 Task 1）
- `MemoryTask`（任务定义）
- `tool_history: list[dict]`（主任务阶段的工具历史）

**Builder 输出：**
- 结构化 reflection prompt（str 或 dict）
- 包含：failure_reason, likely_mistake, retry_strategy, should_reread_target, minimal_next_action

**设计约束：**
- [ ] reflection prompt 长度受控（不超过 reflection_max_tokens）
- [ ] 不包含全量 messages / tool results
- [ ] 只包含摘要信息
- [ ] 缺少某些字段时能降级工作

**测试先写：**
- `tests/test_reflection_builder.py`

**测试覆盖：**
- [ ] reflection prompt 不为空
- [ ] 输入包含 failure / tool summary / memory summary
- [ ] 输入长度受控
- [ ] observation/artifact 不会被无脑全量灌入
- [ ] builder 在缺少某些字段时也能降级工作
- [ ] 输出格式包含所有必要字段

**验收标准：**
- [ ] reflection 输入是 bounded 的
- [ ] 不破坏 Phase 3.2E 的 observation budget 设计
- [ ] 能稳定输出结构化 reflection prompt

---

### 任务卡 3（Phase 1）：Benchmark Integration with One-Shot Reflection Retry

**目标：** 在 MemoryExperiment 层实现 one-shot reflection retry，对比 baseline vs reflection。

**建议改动文件：**
- `src/agent/evaluation/memory_experiment.py`
- `scripts/run_phase32_memory_eval.py`

**建议新增文件：**
- `tests/test_reflection_eval_runner.py`

**实现方式：**

```
_run_scripted_task(config, task, reflection_config):
    # Phase 1: first attempt
    first_result = run_first_attempt(config, task)

    # Phase 2: 判定是否需要 reflection
    decision = policy.should_reflect(task, first_result)

    if decision.should_reflect and reflection_config.enabled:
        # Phase 3: 构造 reflection prompt
        reflection_prompt = builder.build(task, first_result, tool_history)

        # Phase 4: second attempt（用 task 的 retry_script）
        second_result = run_retry_attempt(config, task, reflection_prompt)

        # 记录 reflection 元数据
        return {
            **second_result,
            "reflection_triggered": True,
            "reflection_reason": decision.reason,
            "first_attempt_correct": first_result["correct"],
            "first_attempt_tool_calls": first_result["tool_calls"],
        }
    else:
        return {
            **first_result,
            "reflection_triggered": False,
        }
```

**MemoryTask 扩展：**
- 新增可选字段 `retry_script: list[list[dict]] | None`
- 如果 task 没有 retry_script，reflection 不触发（跳过）
- retry_script 是固定的 deterministic 行为

**新增指标：**
- `reflection_trigger_rate`：触发 reflection 的任务比例
- `reflection_retry_success_rate`：reflection 后重试成功的比例
- `reflection_avg_extra_tool_calls`：reflection 引入的额外 tool calls
- `first_to_second_correctness_gain`：第一次→第二次的正确率提升
- `reflection_helped_tasks`：reflection 确实帮助了的任务数

**Runner 增强：**
- `run_phase32_memory_eval.py` 支持 `--with-reflection` 选项
- 输出 baseline vs reflection 并列对比

**测试先写：**
- `tests/test_reflection_eval_runner.py`

**测试覆盖：**
- [ ] runner 输出 reflection 配置结果
- [ ] JSON schema 稳定（包含 reflection 指标）
- [ ] markdown 报告出现 reflection 段落
- [ ] baseline vs reflection 能并列输出
- [ ] 没有真实 API key 也能跑
- [ ] reflection disabled 时行为与 baseline 完全一致
- [ ] 没有 retry_script 的 task 不触发 reflection

**验收标准：**
- [ ] 能做 before/after 比较（memory_on vs memory_on+reflection）
- [ ] 输出 markdown + json
- [ ] reflection 指标可追踪
- [ ] 默认本地运行不依赖真实 API key
- [ ] 不破坏现有 memory_on / memory_off / memory_irrelevant 对比

---

### 任务卡 4（Phase 2）：Loop Integration（仅在 Phase 1 证明有效后）

**目标：** 将 reflection 接入 AgentLoop，让真实 agent 也能用。

**状态：⏸️ 延后，不进入 Phase 1 实现。**

**如果 Phase 1 benchmark 证明 reflection 有效，需要做的事：**
- LoopConfig 新增 reflection 相关字段
- AgentLoop.run() 支持 post-run evaluation + retry
- 真实 agent 的 failure detection（保守 heuristic）：
  - tool_calls 超阈值
  - 重复读取 / 重复搜索
  - 工具错误后仍产出弱回答
  - 明显低置信文本
  - 接近或触发 max_turns
- 不用 LLM 自评作为主触发器

**暂不实现的原因：**
- benchmark 层有 verifier，可以准确判断失败
- 真实 agent 没有 verifier，failure detection 更复杂
- 先用 benchmark 证明价值，再改核心代码

---

### 任务卡 5（Phase 2）：文档固化（仅在 Phase 1 证明有效后）

**目标：** 把 Reflection 的定位写清楚，防止被写成"自进化智能体"。

**建议更新文件：**
- `docs/agent-improvement/04-testing-record.md`
- `docs/agent-improvement/05-interview-qa.md`
- `docs/agent-improvement/07-next-roadmap.md`
- 新增：`docs/agent-improvement/17-phase3.2c-controlled-reflection.md`

**文档必须写清楚：**
- ✅ 可以写：bounded reflection, one-shot retry, controlled self-correction, benchmark-backed improvement
- ❌ 不能写：self-evolving agent, autonomous self-improvement, Hermes-level learning loop, automatic skill growth

**验收标准：**
- [ ] README/文档口径不夸大
- [ ] 明确说明与 Hermes 的区别
- [ ] 明确说明 Reflection 是"受控纠错"，不是"长期进化"
- [ ] benchmark 结果诚实呈现（包括"无提升"的情况）

---

## 量化目标

Phase 3.2E 基线（来自 `.agent/eval_phase32e_followup_review/`）：

| 指标 | memory_on | memory_off |
|------|-----------|------------|
| correct_rate | 70% | 63% |
| memory_dependent_success_rate | 63% | 53% |
| avg_tool_calls | 0.1 | 1.0 |
| target_reread_rate | 0% | 100% |
| answer_without_reread_rate | 72% | 0% |

Phase 3.2C 目标（诚实可比较，不强求提升）：
- memory_on_reflection.correct_rate >= memory_on.correct_rate
- memory_on_reflection.memory_dependent_success_rate 有小幅提升
- memory_on_reflection.avg_tool_calls 不要恶化太多
- 如果完全无提升，诚实写清结论

---

## 测试命令

```bash
# Phase 1 测试
uv run pytest tests/test_reflection_policy.py -q
uv run pytest tests/test_reflection_builder.py -q
uv run pytest tests/test_reflection_eval_runner.py -q

# 回归测试
uv run pytest tests/test_memory_experiment.py -q

# 全量测试
uv run pytest tests -q

# Benchmark
uv run python scripts/run_phase32_memory_eval.py
uv run python scripts/run_phase32_memory_eval.py --with-reflection
```

---

## 审核标准

- [ ] reflection 是可开关的
- [ ] 每任务最多只允许一次 reflection retry
- [ ] reflection 输入是 budget-controlled 的
- [ ] benchmark 能输出 baseline vs reflection 对比
- [ ] 默认本地运行不依赖真实 API key
- [ ] 全量测试继续为绿
- [ ] 文档明确写成"controlled reflection"，不是"自进化"
- [ ] Phase 1 不改 AgentLoop 核心代码
