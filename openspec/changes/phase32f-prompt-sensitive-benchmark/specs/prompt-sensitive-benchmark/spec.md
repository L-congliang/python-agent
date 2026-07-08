## Overview

Phase 3.2F: Prompt-Sensitive Reflection Benchmark Hardening

让 retry 行为真正对 reflection prompt 内容敏感，建立从"reflection 内容"到"retry 行为"的完整因果链。

**定位：** prompt-sensitive scripted benchmark，不是 real-model benchmark。

## Core Concepts

### PromptAwareScriptedModelClient

根据 reflection prompt 中的 `retry_strategy` 字段选择不同 retry branch。

```python
class PromptAwareScriptedModelClient:
    def __init__(
        self,
        branches: dict[str, list[list[dict]]],  # branch_name -> rounds
        default_branch: str,
    ): ...
    def chat_stream(self, messages, system="", **kwargs) -> StreamResult: ...
    def _extract_strategy(self, messages) -> str: ...  # 从 prompt 提取 retry_strategy
```

路由逻辑：
1. 从最后一条 user message 提取 `retry_strategy: xxx`
2. 查找 branches[xxx]，如果找到则用该 branch
3. 如果未找到，fallback 到 default_branch

### ReflectionPlan

ReflectionBuilder 的结构化输出，分离"给模型的文本"和"给 harness 的控制信号"。

```python
@dataclass
class ReflectionPlan:
    prompt: str              # 给模型/agent 的反思文本
    retry_strategy: str      # 给 benchmark harness 的 routing 信号
    should_reread_target: bool
```

### retry_branches

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

### 三组对比（同一子集、memory_off 基线）

| 组 | 配置 | 任务范围 | 验证什么 |
|----|------|---------|---------|
| Subset Baseline | memory_off，无 retry | 子集 | 子集基准 |
| Subset Scripted Retry | memory_off + 固定 retry | 子集 | retry 机制本身 |
| Subset Prompt-Sensitive | memory_off + prompt-sensitive retry | 子集 | reflection 内容增量 |

比较（三组使用同一任务子集，delta 只反映机制差异）：
- Subset Baseline vs Subset Scripted = retry 机制收益
- Subset Scripted vs Subset Prompt-Sensitive = reflection 内容增量
- Subset Baseline vs Subset Prompt-Sensitive = 完整 pipeline 总效果

可选：Full Baseline（全量 27 任务，memory_off）做背景展示，不参与 delta。

## Data Flow

```
MemoryExperiment._run_scripted_task(config, task, reflection_config)
  ↓
First attempt（deterministic baseline，不变）
  ↓
Verifier 判定 → ReflectionPolicy.should_reflect()
  ↓
如果触发：
  ReflectionBuilder.build(summary) → ReflectionPlan
    ↓
  PromptAwareScriptedModelClient(
    branches=task.retry_branches,
    default_branch=task.default_retry_branch,
  )
    ↓
  chat_stream() → 解析 retry_strategy → 选 branch → 执行
    ↓
  Verifier 判定 retry 结果
```

## Testing Strategy

### test_fake_client.py

- 根据 prompt 中的 retry_strategy 选 branch
- 默认 fallback 到 default_branch
- prompt 无 strategy 时用 default
- 不同 branch 产生不同行为

### test_reflection_builder.py

- build() 返回 ReflectionPlan
- prompt 非空
- retry_strategy 是有效值
- should_reread_target 正确

### test_reflection_eval_runner.py

- 三组对比输出完整
- JSON 包含三组结果
- delta 指标正确计算

## Constraints

**做：**
- PromptAwareScriptedModelClient 根据 prompt 内容选 branch
- ReflectionBuilder 输出结构化 ReflectionPlan
- 三组对比拆开 retry 机制和 reflection 内容的贡献
- default_retry_branch fallback
- 只在 reflection-sensitive 子集上跑三组

**不做：**
- 改 AgentLoop
- 改 first attempt 行为
- 大规模 real-model benchmark
- recursive reflection
- 自由文本理解（保持 deterministic）
