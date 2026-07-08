## Phase 3.2F: Prompt-Sensitive Reflection Benchmark Hardening

### 执行策略

**3 个任务卡，严格按顺序：**
- Task 1: PromptAwareScriptedModelClient + ReflectionPlan
- Task 2: Task 层 retry_branches + Benchmark 三组对比
- Task 3: 文档固化

---

### 任务卡 1：PromptAwareScriptedModelClient + ReflectionPlan

**目标：** 让 retry 行为真正对 reflection prompt 内容敏感。

**建议改动文件：**
- `src/agent/evaluation/fake_client.py` — 新增 PromptAwareScriptedModelClient
- `src/agent/reflection/types.py` — 新增 ReflectionPlan
- `src/agent/reflection/builder.py` — build() 返回 ReflectionPlan

**PromptAwareScriptedModelClient 设计：**

```python
class PromptAwareScriptedModelClient:
    """根据 reflection prompt 中的 retry_strategy 字段选择不同 retry branch。

    用法:
        client = PromptAwareScriptedModelClient(
            branches={
                "use_memory_answer": [rounds...],
                "reread_then_answer": [rounds...],
            },
            default_branch="use_memory_answer",
        )
    """

    def __init__(
        self,
        branches: dict[str, list[list[dict[str, Any]]]],
        default_branch: str,
    ) -> None:
        self._branches = branches
        self._default_branch = default_branch
        self._index = 0
        self.prompts: list[str] = []
        self.supports_prompt_cache: bool = False
        self.last_completion_metadata: dict[str, Any] = {}
        self._selected_branch: str = default_branch

    def chat_stream(self, messages, system="", **kwargs) -> StreamResult:
        # 首次调用时：从最后一条 user message 解析 retry_strategy
        if self._index == 0:
            self._selected_branch = self._extract_strategy(messages)

        # 用选中的 branch 执行
        rounds = self._branches.get(self._selected_branch, self._branches[self._default_branch])
        ...

    def _extract_strategy(self, messages) -> str:
        """从 messages 中提取 retry_strategy 字段"""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = str(msg.get("content", ""))
                for line in content.split("\n"):
                    if line.strip().startswith("retry_strategy:"):
                        return line.split(":", 1)[1].strip()
        return self._default_branch
```

**ReflectionPlan 设计：**

```python
@dataclass
class ReflectionPlan:
    """ReflectionBuilder 的结构化输出"""
    prompt: str              # 给模型/agent 的反思文本
    retry_strategy: str      # 给 benchmark harness 的 routing 信号
    should_reread_target: bool
```

**Builder 改动：**
- `ReflectionBuilder.build()` 返回 `ReflectionPlan` 而不是 `str`
- prompt 字段包含完整的反思文本
- retry_strategy 字段根据触发类型和 task 特征选择

**测试先写：**
- `tests/test_fake_client.py` — 测试 PromptAwareScriptedModelClient
  - 根据 prompt 中的 retry_strategy 选 branch
  - 默认 fallback 到 default_branch
  - prompt 无 strategy 时用 default
  - 不同 branch 产生不同行为
- `tests/test_reflection_builder.py` — 测试 ReflectionPlan 输出
  - build() 返回 ReflectionPlan
  - prompt 非空
  - retry_strategy 是有效值
  - should_reread_target 正确

**验收标准：**
- PromptAwareScriptedModelClient 根据 prompt 内容选 branch
- ReflectionBuilder 输出结构化 ReflectionPlan
- default_retry_branch fallback 正常工作
- 不破坏现有测试

---

### 任务卡 2：Task 层 retry_branches + Benchmark 三组对比

**目标：** 让 task 定义所有合法 retry 路径，benchmark 做三组对比。

**建议改动文件：**
- `src/agent/evaluation/memory_experiment.py` — MemoryTask 新增 retry_branches，run 支持三组对比
- `scripts/run_phase32_memory_eval.py` — 支持三组输出

**MemoryTask 扩展：**

```python
@dataclass
class MemoryTask:
    ...
    # Phase 3.2C: 单路径 retry（保留向后兼容）
    retry_script: list[list[dict[str, Any]]] | None = None
    # Phase 3.2F: 多路径 retry（prompt-sensitive）
    retry_branches: dict[str, list[list[dict[str, Any]]]] | None = None
    default_retry_branch: str = "use_memory_answer"
```

**三组对比设计（同一子集、memory_off 基线）：**

| 组 | 配置 | 任务范围 | 验证什么 |
|----|------|---------|---------|
| Subset Baseline | memory_off，无 retry | 子集 | 子集上的基准 |
| Subset Scripted Retry | memory_off + 固定 retry | 子集 | retry 机制本身 |
| Subset Prompt-Sensitive | memory_off + prompt-sensitive retry | 子集 | reflection 内容增量 |

**为什么用 memory_off：** memory_on 本来就接近最优，测不出增量。memory_off 才会真实触发 retry。

**为什么同一子集：** 分母不同 → delta 混入任务集差异。同一子集 → delta 只反映机制差异。

**可选：Full Baseline（全量 27 任务）做背景展示，不参与 delta。**

**reflection-sensitive 子集：** 有 retry_branches 的任务（当前是 3 个 memory_sensitive 任务）

**新增指标：**
- `subset_baseline_correct`：子集基准正确率
- `subset_scripted_delta`：scripted retry vs baseline 的差异
- `subset_prompt_sensitive_delta`：prompt-sensitive vs scripted 的差异（= reflection 内容增量）
- `subset_total_delta`：完整 pipeline vs baseline 的总效果

**Runner 增强：**
- `--with-reflection` 默认输出三组对比
- 只在 reflection-sensitive 子集上跑 Group 2/3

**测试先写：**
- `tests/test_reflection_eval_runner.py` — 测试三组对比输出
  - JSON 包含三组结果
  - 每组有完整指标
  - delta 指标正确计算

**验收标准：**
- 三组对比能区分 retry 机制和 reflection 内容的贡献
- 运行时间可控（只在子集上跑三组）
- JSON + MD 输出完整

---

### 任务卡 3：文档固化

**目标：** 写清 Phase 3.2F 的定位和结论。

**建议更新文件：**
- 新增：`docs/agent-improvement/18-phase3.2f-prompt-sensitive-benchmark.md`
- 更新：`docs/agent-improvement/04-testing-record.md`
- 更新：`docs/agent-improvement/07-next-roadmap.md`

**必须写清：**
- Phase 3.2F 证明了什么（prompt-sensitive retry 的因果链）
- 三组对比的结论（retry 机制 vs reflection 内容各自的贡献）
- 边界说明（scripted benchmark，不是 real-model benchmark）
- 下一步建议（selective real-model eval 或 loop integration）

**验收标准：**
- 口径不夸大
- 三组对比结论诚实呈现
- 边界说明保留

---

## 量化目标

Phase 3.2F 的目标不是"做出漂亮数字"，而是"拆开因果链"。

**如果 Group 2 ≈ Group 3：** reflection 内容无增量，只是重试有效。诚实写清。

**如果 Group 3 > Group 2：** reflection 内容本身有因果价值。量化增量。

**如果 Group 3 < Group 2：** reflection 内容反而干扰了 retry。调查原因。

---

## 测试命令

```bash
uv run pytest tests/test_fake_client.py -q
uv run pytest tests/test_reflection_builder.py -q
uv run pytest tests/test_reflection_eval_runner.py -q
uv run pytest tests/test_memory_experiment.py -q
uv run pytest tests -q
uv run python scripts/run_phase32_memory_eval.py --with-reflection
```
