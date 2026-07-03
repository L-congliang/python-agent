# P6 Prompt Ablation Experiment

## 实验目的

对比不同 prompt 版本的工具选择准确率，验证 System Prompt 优化效果。

## 实验配置

| 配置 | 说明 |
|------|------|
| baseline | 最简 prompt（只写工具列表） |
| +identity | 加 Identity 部分 |
| +tool_guide | 加 Tool Selection Guide |
| +full | 完整优化 prompt |

## 测试任务集

共 22 个任务，覆盖所有工具类型。

## 结果

| 配置 | tool_accuracy | avg_prompt_tokens |
|------|---------------|-------------------|
| baseline | 13.6% | 76 |
| +identity | 59.1% | 33 |
| +tool_guide | 27.3% | 53 |
| +full | 59.1% | 47 |

## 结论

最优配置: **+identity** (tool_accuracy=59.1%)
相比 baseline 提升: **333.3%**