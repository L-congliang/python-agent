## Context

Phase 3.2C Phase 1 证明了 policy-triggered scripted retry 有局部效率收益，但 ScriptedModelClient 不根据 reflection prompt 内容分支。Phase 3.2F 让 retry 行为真正对 reflection 内容敏感，建立完整因果链。

## Goals / Non-Goals

**Goals:**
- 让 reflection prompt 内容真正影响 retry 行为
- 三组对比拆开 retry 机制和 reflection 内容各自的贡献
- 保持 first attempt baseline 不变
- 保持 deterministic + 可测试

**Non-Goals:**
- 不改 AgentLoop
- 不改 first attempt 行为
- 不做大规模 real-model benchmark
- 不做 recursive reflection

## Decisions

### D1：PromptAwareScriptedModelClient — 解析结构化字段选 branch

**选择：Client 解析 ReflectionPlan 的 retry_strategy 字段，选对应 branch。**

```python
class PromptAwareScriptedModelClient:
    def __init__(
        self,
        branches: dict[str, list[list[dict]]],
        default_branch: str,
    ):
        self._branches = branches
        self._default_branch = default_branch

    def chat_stream(self, messages, system="", **kwargs):
        # 从最后一条 user message 提取 retry_strategy
        strategy = self._extract_strategy(messages)
        branch_key = strategy if strategy in self._branches else self._default_branch
        rounds = self._branches[branch_key]
        # 按选中的 branch 执行
        ...
```

**为什么不用纯关键词 if-else：**
- 结构化字段更稳定（不依赖 prompt 措辞）
- 更容易测试（断言 strategy 值，不用 grep 文本）
- 以后演进更容易（routing metadata 和 prompt 文本分离）

**为什么不用自由文本理解：**
- 保持 deterministic
- benchmark 目标是验证机制，不是模拟模型自省

### D2：ReflectionPlan — Builder 的结构化输出

**选择：ReflectionBuilder.build() 返回 ReflectionPlan，不是 str。**

```python
@dataclass
class ReflectionPlan:
    prompt: str              # 给模型/agent 的反思文本
    retry_strategy: str      # 给 benchmark harness 的 routing 信号
    should_reread_target: bool
```

**为什么结构化：**
- prompt 是给模型的文本，retry_strategy 是给 harness 的控制信号
- 两种层级的信息不应混在一段纯文本里
- 更容易测试和演进

### D3：retry_branches — Task 定义所有合法 retry 路径

**选择：MemoryTask 新增 retry_branches dict，定义所有可能的 retry 行为。**

```python
MemoryTask(
    ...
    retry_branches={
        "use_memory_answer": [
            [{"type": "text", "text": "db.prod.internal"}],
        ],
        "reread_then_answer": [
            [{"type": "tool_use", "id": "call_1", "name": "read",
              "input": {"file_path": ".../database.py"}}],
            [{"type": "text", "text": "db.prod.internal"}],
        ],
    },
    default_retry_branch="use_memory_answer",
)
```

**为什么用 dict 而不是 list：**
- 每个 branch 有明确的 key（对应 retry_strategy 的值）
- Client 只做 key 查找，不做自由理解
- Task 定义所有合法路径，Client 只负责选

### D4：三组对比 — 同一子集、会真实触发 retry 的配置

**选择：三组都在 reflection-sensitive 子集上跑，用 memory_off 作为基线配置。**

| 组 | 配置 | 任务范围 | 验证什么 |
|----|------|---------|---------|
| Subset Baseline | memory_off，无 retry | 子集 | 子集上的基准 |
| Subset Scripted Retry | memory_off + 固定 retry | 子集 | retry 机制本身的收益 |
| Subset Prompt-Sensitive | memory_off + prompt-sensitive retry | 子集 | reflection 内容的增量价值 |

**为什么用 memory_off 而不是 memory_on：**
- memory_on 本来就接近最优，first attempt 几乎不需要纠正
- memory_off 才会真实触发 retry（reread、incorrect）
- 如果用 memory_on，三组可能都 ≈ baseline，测不出增量

**为什么三组必须用同一任务子集：**
- 分母不同 → delta 混入任务集差异，不再是纯机制差异
- 同一子集 → delta 只反映机制差异

**可选：额外跑 Full Baseline（全量 27 任务）做整体背景展示，不参与 delta 计算。**

**比较方式：**
- Subset Baseline vs Subset Scripted = "one-shot retry 机制本身有没有用"
- Subset Scripted vs Subset Prompt-Sensitive = "reflection 内容有没有额外价值"
- Subset Baseline vs Subset Prompt-Sensitive = "完整 reflection pipeline 的总效果"

**如果 Subset Scripted ≈ Subset Prompt-Sensitive → reflection 内容无增量，只是重试有效**
**如果 Subset Prompt-Sensitive > Subset Scripted → reflection 内容本身有因果价值**

**reflection-sensitive 子集定义：** 有 retry_branches 的任务（当前是 3 个 memory_sensitive 任务）

### D5：default_retry_branch — 异常 fallback

**选择：必须有 default_retry_branch，解析失败时优雅降级。**

- 正常：按 retry_strategy 走
- builder 异常或字段缺失：回退 default_retry_branch
- 不会把"解析失败"误当成"reflection 无效"

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|------|------|------|
| Group 2 ≈ Group 3 | reflection 内容无增量 | 诚实写清结论，不强行包装 |
| retry_branches 定义不当 | 选错路径 | 先在 2-3 个 task 上手动验证 |
| PromptAwareScriptedModelClient 解析失败 | fallback 到默认 | default_retry_branch 保证不崩 |
| 三组对比运行时间增加 | benchmark 变慢 | 只在子集上跑三组 |
