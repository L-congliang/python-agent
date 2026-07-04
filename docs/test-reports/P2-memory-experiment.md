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
| cross_round_recall | 2 | setup 读文件 → 主阶段只提问 |
| cross_file_dep | 2 | 读 A+B → 改 A，正确修改依赖 B |
| multi_round_edit | 2 | 多步修改同组文件 |
| noise | 2 | 注入噪声 → 问正确对象 |

## 指标定义

| 指标 | 定义 |
|------|------|
| correct_rate | verifier 判定正确的任务比例 |
| repeated_reads | 同一文件第 2 次及以后成功读取的总次数 |
| memory_hit_rate | 有 setup_turns 的任务中，主阶段未 reread 目标文件的比例 |
| avg_tool_calls | 平均每任务工具调用次数 |
| avg_duration | 平均每任务耗时（秒） |

## 实验结果

### V1 修复后（2026-07-04，ContextManager 接入 + 去重 + 路径归一化）

| 配置 | correct_rate | repeated_reads | memory_hit_rate | avg_tool_calls | avg_duration |
|------|-------------|----------------|-----------------|----------------|--------------|
| memory_on | **100%** | 1 | 40% (10 eligible) | 2.3 | 14.8s |
| memory_off | 100% | 0 | 60% (10 eligible) | 2.1 | 12.0s |

### V1 退化版（2026-07-04，ContextManager 接入但有 bug）

| 配置 | correct_rate | repeated_reads | memory_hit_rate | avg_tool_calls | avg_duration |
|------|-------------|----------------|-----------------|----------------|--------------|
| memory_on | 86% | 0 | 44% (9 eligible) | 2.0 | 13.1s |
| memory_off | 86% | 1 | 60% (10 eligible) | 2.1 | 14.2s |

### V0 基线（2026-07-04，升级任务集后）

| 配置 | correct_rate | repeated_reads | memory_hit_rate | avg_tool_calls | avg_duration |
|------|-------------|----------------|-----------------|----------------|--------------|
| memory_on | 100% | 1 | 50% (10 eligible) | 2.2 | 14.4s |
| memory_off | 86% | 1 | 50% (10 eligible) | 2.2 | 14.4s |
| memory_irrelevant | 93% | 2 | 60% (10 eligible) | 2.3 | 14.3s |

## V1 修复记录

**问题 1：history + current_request 重复注入。** format_history(self._messages) 包含了最后一条 user 消息，随后又单独提取 current_request，导致当前请求在 prompt 中出现两次，浪费 token 并增加截断概率。修复：history 排除最后一条 user 消息。

**问题 2：file_summaries 的 recent_files 优先规则失效。** touch_file() 存相对路径，update_file_summary() 存绝对路径，导致 path in recent 永远匹配不上。修复：select_relevant_file_summaries() 做 basename + normpath 双重匹配。

**问题 3（未修）：budget 裁剪顺序。** tools(2000) 在 memory(1600) 之前被裁。本次实验 metadata 显示零截断，暂不需要调。

## 结论

- V1 改造方向正确，修复后 memory_on 回到 100%
- ContextManager 零截断（所有 section 都在预算内）
- history 去重和路径归一化是关键修复
- 下一步：跑三轮稳定实验，确认结果可复现
