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
| L3 | 5 | 记忆显著提升效率 |
| L4 | 5 | 没有记忆几乎不可能答对 |

## 测试场景

| 类别 | 数量 | 说明 |
|------|------|------|
| history_reference | 2 | 有 setup_turns，验证 memory_hit |
| edit_dependency | 4 | fixture 文件，验证 file_changed |
| cross_round_recall | 3 | 跨轮事实回忆，验证 memory_hit |
| cross_file_dep | 3 | 跨文件依赖修改，验证 file_changed |
| multi_round_edit | 3 | 多轮连续改动，验证 multi_file_changed |
| noise | 3 | 噪声干扰与错误纠偏，验证抗混淆能力 |

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
| memory_irrelevant | 94% | 90% (9/10) | 6% | 100% | 1.7 | 12.7s | ⚠️ 1 个异常任务 |

## ⚠️ 无 clean rounds

**所有轮次都存在异常任务，无法得出正式结论。**

## ⚠️ 异常任务汇总

以下 config 存在异常任务，不纳入正式统计：

### memory_irrelevant（1 个异常任务）

| task_id | failed_reason | abnormal_reason |
|---------|---------------|-----------------|
| recall_rate_limit | api_429 | API 429 rate limited |

## 各任务详情（按 L1-L4 分组）

### L4 任务（5 个）

#### memory_irrelevant ⚠️

| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |
|---------|----------|---------|----------------|------------|------------|----------|---------------|
| disambiguate_db_vs_cache_secret | noise | ✅ | 0 | 1 | 0 | 7.6s |  |
| delayed_constraint_single_file_edit | edit_dependency | ✅ | 0 | 1 | 1 | 10.0s |  |
| cross_file_literal_recall_no_import | cross_file_dep | ✅ | 0 | 0 | 2 | 20.0s |  |
| multi_round_edit_after_noise | multi_round_edit | ✅ | 0 | 1 | 2 | 20.1s |  |
| edit_using_previous_fact_only | edit_dependency | ✅ | 0 | 0 | 2 | 12.5s |  |

### L3 任务（5 个）

#### memory_irrelevant ⚠️

| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |
|---------|----------|---------|----------------|------------|------------|----------|---------------|
| recall_api_key | cross_round_recall | ✅ | 0 | 1 | 0 | 7.2s |  |
| recall_rate_limit | cross_round_recall | ❌ | 0 | n/a | 0 | 11.2s | api_429 |
| dep_use_api_key | cross_file_dep | ✅ | 0 | 0 | 2 | 15.4s |  |
| dep_update_header | cross_file_dep | ✅ | 0 | 0 | 2 | 12.5s |  |
| forbidden_reread_fact_answer | cross_round_recall | ✅ | 0 | 1 | 0 | 7.1s |  |

### L2 任务（7 个）

#### memory_irrelevant ⚠️

| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |
|---------|----------|---------|----------------|------------|------------|----------|---------------|
| history_loop_config | history_reference | ✅ | 0 | 1 | 0 | 8.2s |  |
| history_manager_class | history_reference | ✅ | 0 | 1 | 0 | 19.2s |  |
| edit_config_update | edit_dependency | ✅ | 1 | n/a | 4 | 11.5s |  |
| multi_add_timeout | multi_round_edit | ✅ | 0 | 0 | 6 | 16.4s |  |
| multi_add_validation | multi_round_edit | ✅ | 0 | 1 | 2 | 14.0s |  |
| noise_db_config | noise | ✅ | 0 | 0 | 2 | 13.5s |  |
| noise_cache_port | noise | ✅ | 0 | 0 | 2 | 11.6s |  |

### L1 任务（1 个）

#### memory_irrelevant ⚠️

| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |
|---------|----------|---------|----------------|------------|------------|----------|---------------|
| edit_main_function | edit_dependency | ✅ | 0 | n/a | 3 | 10.7s |  |
