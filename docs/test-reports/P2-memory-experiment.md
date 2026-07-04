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

### V1 基线（2026-07-04，ContextManager 接入后）

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

## V1 退化分析

**退化任务：**
- `fact_manager_methods`: ❌ (was ✅), 0 tool_calls, 4.3s — 模型从记忆"猜"答案，猜错
- `history_loop_config`: ❌ (was ✅), 0 tool_calls, 2.7s — 同上

**退化原因假设：**
1. ContextManager 预算裁剪压缩了 tools section，模型对可用工具理解变弱
2. 分层记忆注入改变了 prompt 结构，模型行为受影响
3. history formatter 摘要化丢失了关键上下文

**修复方向：**
- 检查 ContextMetadata 中各 section 的 rendered_tokens 和 was_truncated
- 调整 budget 分配或 memory 组装策略
- 确保 tools section 不被过度压缩
