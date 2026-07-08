# Phase 3.2F: Prompt-Sensitive Reflection Benchmark Hardening

更新时间：2026-07-08

## 1. 阶段目标

让 retry 行为真正对 reflection prompt 内容敏感，建立从"reflection 内容"到"retry 行为"的完整因果链。

**定位：** prompt-sensitive scripted benchmark，不是 real-model benchmark。

## 2. 解决的核心问题

Phase 3.2C Phase 1 已证明 policy-triggered scripted retry 有局部效率收益，但 ScriptedModelClient 按固定 rounds 执行，不根据 reflection prompt 内容分支。

**问题：** 当前收益可能来自"第二次重试"机制本身，而非 reflection 内容。

**解决：** 引入 PromptAwareScriptedModelClient，根据 reflection prompt 中的 `retry_strategy` 字段选择不同 retry branch。

## 3. 核心交付

### 3.1 PromptAwareScriptedModelClient

根据 reflection prompt 中的 `retry_strategy` 字段选择不同 retry branch。

```python
client = PromptAwareScriptedModelClient(
    branches={
        "use_memory_answer": [rounds...],
        "reread_then_answer": [rounds...],
    },
    default_branch="use_memory_answer",
)
```

路由逻辑：
1. 从最后一条 user message 提取 `retry_strategy: xxx`
2. 查找 branches[xxx]，如果找到则用该 branch
3. 如果未找到，fallback 到 default_branch

### 3.2 ReflectionPlan

ReflectionBuilder 的结构化输出，分离"给模型的文本"和"给 harness 的控制信号"。

```python
@dataclass
class ReflectionPlan:
    prompt: str              # 给模型/agent 的反思文本
    retry_strategy: str      # 给 benchmark harness 的 routing 信号
    should_reread_target: bool
```

### 3.3 retry_branches

MemoryTask 的多路径 retry 定义。每个 branch 是一个 script（rounds 列表）。

```python
MemoryTask(
    retry_branches={
        "use_memory_answer": [[{"type": "text", "text": "..."}]],
        "reread_then_answer": [[{"type": "tool_use", ...}], [{"type": "text", ...}]],
    },
    default_retry_branch="use_memory_answer",
)
```

### 3.4 三组对比 benchmark

| 组 | 配置 | 任务范围 | 验证什么 |
|----|------|---------|---------|
| Subset Baseline | memory_off，无 retry | 子集 | 子集基准 |
| Subset Scripted Retry | memory_off + 固定 retry | 子集 | retry 机制本身 |
| Subset Prompt-Sensitive | memory_off + prompt-sensitive retry | 子集 | reflection 内容增量 |

三组使用同一任务子集（reflection-sensitive 任务），delta 只反映机制差异。

## 4. 实验结果

### 三组对比结果（3 个 memory_sensitive 任务）

| 组 | correct | reread | no_reread | tools |
|----|---------|--------|-----------|-------|
| Subset Baseline | 100% | 100% | 0% | 1.0 |
| Subset Scripted Retry | 100% | 0% | 100% | 1.0 |
| Subset Prompt-Sensitive | 100% | 0% | 100% | 1.0 |

**Delta 分析：**
- Scripted vs Baseline: reread -100%（retry 机制消除了 reread）
- Prompt-Sens vs Scripted: reread +0%（reflection 内容无额外增量）
- Prompt-Sens vs Baseline: reread -100%（完整 pipeline 效果）

**结论：**
- ✅ retry 机制本身有效（消除了 reread）
- ⚠️ reflection 内容在此子集上无额外增量（scripted 和 prompt-sensitive 效果相同）
- ✅ PromptAwareScriptedModelClient 正确路由（选对了 branch）

### 为什么 reflection 内容无额外增量？

这 3 个 memory_sensitive 任务的特征是：
- setup_turns 告知了正确答案
- memory_on 直接回答（不 reread）
- memory_off 必须 reread

scripted retry 和 prompt-sensitive retry 都选择了 "use_memory_answer" 策略（跳过 reread），所以效果相同。reflection 内容的增量价值在这些"简单纠错"场景下为零——这恰恰说明 routing 正确工作了。

**如需观察 reflection 内容的增量价值，需要更复杂的任务：**
- 第一次答错的原因不是"reread 了"，而是"读错了文件"或"理解错了"
- 这时 prompt-sensitive retry 可以选择 "reread_then_answer" 而不是 "use_memory_answer"
- scripted retry 则始终用固定策略

## 5. 改动文件清单

| 文件 | 类型 |
|------|------|
| `src/agent/evaluation/fake_client.py` | 修改（新增 PromptAwareScriptedModelClient） |
| `src/agent/reflection/types.py` | 修改（新增 ReflectionPlan） |
| `src/agent/reflection/builder.py` | 修改（返回 ReflectionPlan） |
| `src/agent/evaluation/memory_experiment.py` | 修改（retry_branches、PromptAwareClient 集成） |
| `scripts/run_phase32_memory_eval.py` | 修改（--three-group 选项） |
| `tests/test_reflection_builder.py` | 修改（适配 ReflectionPlan） |
| `tests/test_reflection_eval_runner.py` | 修改（新增 PromptAwareClient 测试） |
| `docs/agent-improvement/18-phase3.2f-prompt-sensitive-benchmark.md` | 新增 |

## 6. 测试覆盖

**新增/修改测试：**
- `test_prompt_aware_client_selects_branch` — 根据 prompt 中的 retry_strategy 选 branch
- `test_prompt_aware_client_fallback_to_default` — 无 strategy 时 fallback
- `test_retry_client_receives_reflection_prompt` — retry 收到 reflection 内容
- `test_build_returns_reflection_plan` — Builder 返回 ReflectionPlan
- `test_reread_triggers_use_memory_strategy` — reread → use_memory_answer
- `test_incorrect_without_reread_triggers_reread_strategy` — 答错 → reread_then_answer

**全量测试：** 1132 passed, 6 skipped

## 7. 边界说明

**当前证明了：**
- ✅ PromptAwareScriptedModelClient 根据 prompt 内容选 branch
- ✅ ReflectionBuilder 输出结构化 ReflectionPlan
- ✅ 三组对比因果拆分成立
- ✅ retry 机制本身有效（消除 reread）

**未证明：**
- ⚠️ reflection 内容在更复杂场景下的增量价值（当前子集太简单）
- ⚠️ 真实模型是否也会因 reflection 提示改变行为（需 selective real-model eval）

**下一步建议：**
- 设计更复杂的 reflection-sensitive 任务（第一次答错不是因为 reread，而是因为理解错误）
- 或做 selective real-model eval 验证外部有效性
