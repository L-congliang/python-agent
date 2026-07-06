# Memory Experiment Report

## 实验设计

- memory_on: memory_enabled=True（完整记忆系统）
- memory_off: memory_enabled=False（真关闭，配置级）
- memory_irrelevant: memory_enabled=True + 注入噪声记忆

## 任务分级统计

| 等级 | 数量 | 说明 |
|------|------|------|
| L1 | 1 | 不需要记忆也能答对 |
| L2 | 7 | 记忆有帮助但不是必须 |
| L3 | 6 | 记忆显著提升效率 |
| L4 | 10 | 没有记忆几乎不可能答对 |

## 测试场景

| 类别 | 数量 | 说明 |
|------|------|------|
| history_reference | 2 | 有 setup_turns，验证 memory_hit |
| edit_dependency | 6 | fixture 文件，验证 file_changed |
| cross_round_recall | 4 | 跨轮事实回忆，验证 memory_hit |
| cross_file_dep | 4 | 跨文件依赖修改，验证 file_changed |
| multi_round_edit | 4 | 多轮连续改动，验证 multi_file_changed |
| noise | 4 | 噪声干扰与错误纠偏，验证抗混淆能力 |

## 指标定义

| 指标 | 定义 | 用途 |
|------|------|------|
| correct_rate | verifier 判定正确的任务比例 | 整体指标 |
| memory_dependent_success_rate | L3/L4 任务的正确率 | **主效果指标** |
| target_reread_rate | 主任务阶段重读目标文件的比例 | 效率指标 |
| answer_without_reread_rate | setup_turns 后不重读就能答对的比例 | 效率指标 |
| repeated_reads | 同一文件第 2 次及以后成功读取的总次数 | 诊断指标 |
| memory_hit_rate | 有 setup_turns 的任务中，主阶段未 reread 目标文件的比例 | 诊断指标（不作为主效果） |
| avg_tool_calls | 平均每任务工具调用次数 | 效率指标 |
| avg_duration | 平均每任务耗时（秒） | 效率指标 |

## 实验结果

| 配置 | correct_rate | memory_dependent_success_rate | target_reread_rate | answer_without_reread_rate | avg_tool_calls | avg_duration | 异常状态 |
|------|-------------|------------------------------|-------------------|---------------------------|---------------|-------------|----------|
| memory_off | 83% | 83% (5/6) | 17% | 80% | 1.8 | 20.2s | ⚠️ 1 个异常任务 |

## ⚠️ 无 clean rounds

**所有轮次都存在异常任务，无法得出正式结论。**

## ⚠️ 异常任务汇总

以下 config 存在异常任务，不纳入正式统计：

### memory_off（1 个异常任务）

| task_id | failed_reason | abnormal_reason |
|---------|---------------|-----------------|
| constraint_then_edit_single_target | api_429 | API 429 rate limited |

## 各任务详情（按 L1-L4 分组）

### L4 任务（10 个）

#### memory_off ⚠️

| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |
|---------|----------|---------|----------------|------------|------------|----------|---------------|
| delayed_dual_constant_edit | edit_dependency | ✅ | 0 | 0 | 2 | 14.4s |  |
| conflict_secret_disambiguation_strict | noise | ✅ | 0 | 1 | 0 | 11.0s |  |
| cross_file_literal_bundle_no_reread | cross_file_dep | ✅ | 0 | 0 | 3 | 18.7s |  |
| resume_multi_edit_after_irrelevant_round | multi_round_edit | ✅ | 2 | 0 | 6 | 46.8s |  |
| constraint_then_edit_single_target | edit_dependency | ❌ | 0 | n/a | 0 | 10.9s | api_429 |

### L3 任务（6 个）

#### memory_off ⚠️

| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |
|---------|----------|---------|----------------|------------|------------|----------|---------------|
| forbidden_reread_multi_fact_answer | cross_round_recall | ✅ | 0 | 1 | 0 | 19.4s |  |

### L2 任务（7 个）

#### memory_off ⚠️

| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |
|---------|----------|---------|----------------|------------|------------|----------|---------------|

### L1 任务（1 个）

#### memory_off ⚠️

| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |
|---------|----------|---------|----------------|------------|------------|----------|---------------|
