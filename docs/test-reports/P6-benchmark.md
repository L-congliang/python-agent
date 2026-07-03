# P6 Benchmark 对比报告

## 实验目的

验证 P6 System Prompt 优化后，整体能力没有退化。

## 实验配置

- 模型: mimo-v2.5-pro
- Benchmark: benchmarks/coding_tasks.json (10 个任务)
- 使用优化后的 System Prompt (Identity + Behavior + Tool Guide)

## 结果

| 指标 | Phase 0 基线 | P6 | 变化 |
|------|-------------|-----|------|
| pass_rate | 40% | 40% | 持平 |
| avg_attempts | 2.6 | 1.7 | -35% |
| avg_tool_steps | 2.0 | 1.4 | -30% |

## 分类统计

| 类别 | Phase 0 | P6 |
|------|---------|-----|
| code-search | - | 3/3 (100%) |
| error-recovery | - | 1/3 (33%) |
| file-edit | - | 0/4 (0%) |

## 结论

- **pass_rate 持平**: 40% vs 40%，没有退化
- **效率提升**: avg_attempts 和 avg_tool_steps 均下降约 30%，说明优化后的 prompt 让模型更快做出正确决策
- **file-edit 问题**: file-edit 类别全部失败，可能与 mimo 的 XML 输出格式有关（模型输出的格式与预期不完全匹配），需要后续优化
