# Memory Experiment Report

## 实验设计

| 配置 | use_memory | use_irrelevant_memory |
|------|------------|----------------------|
| memory_on | True | False |
| memory_off | False | False |
| memory_irrelevant | True | True |

## 测试场景

| 类别 | 数量 |
|------|------|
| fact_lookup | 4 |
| edit_dependency | 4 |
| history_reference | 4 |

## 实验结果

| 配置 | repeated_reads | correct_rate | memory_hit_rate | 总工具调用 | 耗时 |
|------|----------------|--------------|-----------------|-----------|------|
| memory_on | 0 | 100.00% | 50.00% | 24 | 0.00s |
| memory_off | 0 | 100.00% | 0.00% | 24 | 0.00s |
| memory_irrelevant | 0 | 100.00% | 50.00% | 24 | 0.00s |

## 结论

- **memory_on**: 使用记忆系统，正确率 100.00%
- **memory_off**: 不使用记忆，正确率 100.00%
- **memory_irrelevant**: 使用无关记忆，正确率 100.00%
