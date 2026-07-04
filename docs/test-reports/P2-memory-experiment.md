# Memory Experiment Report

## 实验设计

- memory_on: memory_enabled=True（完整记忆系统）
- memory_off: memory_enabled=False（真关闭，配置级）
- memory_irrelevant: memory_enabled=True + 注入噪声记忆

## 测试场景

| 类别 | 数量 | 说明 |
|------|------|------|
| fact_lookup | 2 | 问答类，验证 contains_text |
| history_reference | 2 | 有 setup_turns，验证 memory_hit |
| edit_dependency | 2 | fixture 文件，验证 file_changed |

## 指标定义

| 指标 | 定义 |
|------|------|
| correct_rate | verifier 判定正确的任务比例 |
| repeated_reads | 同一文件第 2 次及以后成功读取的总次数 |
| memory_hit_rate | 有 setup_turns 的任务中，主阶段未 reread 目标文件的比例 |
| avg_tool_calls | 平均每任务工具调用次数 |
| avg_duration | 平均每任务耗时（秒） |

## 三轮稳定结果（2026-07-04）

| 配置 | Round 1 | Round 2 | Round 3 | 均值 |
|------|---------|---------|---------|------|
| **correct_rate** |||||
| memory_on | 100% | 100% | 100% | 100% |
| memory_off | 100% | 100% | 100% | 100% |
| memory_irrelevant | 100% | 100% | 100% | 100% |
| **repeated_reads** |||||
| memory_on | 1 | 1 | 1 | 1.0 |
| memory_off | 0 | 1 | 1 | 0.7 |
| memory_irrelevant | 1 | 1 | 1 | 1.0 |
| **memory_hit_rate** |||||
| memory_on | 100% (2) | 100% (2) | 100% (2) | 100% |
| memory_off | 100% (2) | 100% (2) | 100% (2) | 100% |
| memory_irrelevant | 100% (2) | 100% (2) | 100% (2) | 100% |
| **avg_tool_calls** |||||
| memory_on | 2.2 | 2.2 | 2.3 | 2.2 |
| memory_off | 1.8 | 2.0 | 2.2 | 2.0 |
| memory_irrelevant | 3.0 | 2.2 | 2.7 | 2.6 |
| **avg_duration** |||||
| memory_on | 11.0s | 10.3s | 10.9s | 10.7s |
| memory_off | 10.5s | 10.6s | 10.5s | 10.5s |
| memory_irrelevant | 13.3s | 10.8s | 11.4s | 11.8s |

## 结论

**已验证：**
- 评测框架稳定可靠，三轮结果波动极小
- memory_on / memory_off / memory_irrelevant 三组对照实验可复现
- memory_irrelevant 有轻微开销（avg_tool_calls +0.6, avg_duration +1.3s）
- 指标来自运行时数据（tool_history + verifier），非硬编码

**未验证（当前任务集太简单）：**
- 记忆系统对正确率的提升
- 记忆系统对重复读取的减少
- 记忆系统对工具调用/耗时的优化

**下一步：** 升级任务集，设计"不用记忆会吃亏"的任务类型：
1. 跨轮事实回忆（setup_turns 读文件 → 主阶段只提问）
2. 跨文件依赖修改（记住 A 才能正确改 B）
3. 多轮连续改动（前一轮改签名 → 后一轮补测试）
4. 噪声干扰（注入相似无关信息 → 看是否被带偏）
