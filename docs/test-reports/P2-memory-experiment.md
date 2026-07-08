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
| cross_round_recall | 2 |  |
| cross_file_dep | 2 |  |
| multi_round_edit | 2 |  |
| noise | 2 |  |

## 指标定义

| 指标 | 定义 |
|------|------|
| correct_rate | verifier 判定正确的任务比例 |
| repeated_reads | 同一文件第 2 次及以后成功读取的总次数 |
| memory_hit_rate | 有 setup_turns 的任务中，主阶段未 reread 目标文件的比例 |
| avg_tool_calls | 平均每任务工具调用次数 |
| avg_duration | 平均每任务耗时（秒） |

## 实验结果

| 配置 | correct_rate | repeated_reads | memory_hit_rate | avg_tool_calls | avg_duration | 耗时 |
|------|-------------|----------------|-----------------|---------------|-------------|------|
| memory_on | 93% | 1 | 60% (10 eligible) | 2.1 | 13.2s | 289.0s |
| memory_off | 93% | 1 | 56% (9 eligible) | 2.0 | 12.6s | 280.1s |
| memory_irrelevant | 100% | 1 | 50% (10 eligible) | 2.2 | 12.1s | 273.9s |

## 各任务详情

### memory_on

| task_id | correct | repeated_reads | memory_hit | tool_calls | duration |
|---------|---------|----------------|------------|------------|----------|
| fact_loop_max_turns | ✅ | 0 | n/a | 3 | 6.6s |
| fact_manager_methods | ✅ | 0 | n/a | 3 | 11.3s |
| history_loop_config | ✅ | 0 | 1 | 0 | 6.9s |
| history_manager_class | ✅ | 0 | 1 | 0 | 19.8s |
| edit_main_function | ✅ | 0 | n/a | 3 | 8.5s |
| edit_config_update | ✅ | 1 | n/a | 4 | 9.3s |
| recall_api_key | ❌ | 0 | 1 | 0 | 16.3s |
| recall_rate_limit | ✅ | 0 | 1 | 0 | 9.7s |
| dep_use_api_key | ✅ | 0 | 0 | 3 | 21.5s |
| dep_update_header | ✅ | 0 | 1 | 1 | 11.3s |
| multi_add_timeout | ✅ | 0 | 0 | 6 | 26.5s |
| multi_add_validation | ✅ | 0 | 1 | 2 | 15.9s |
| noise_db_config | ✅ | 0 | 0 | 2 | 12.0s |
| noise_cache_port | ✅ | 0 | 0 | 2 | 9.4s |

### memory_off

| task_id | correct | repeated_reads | memory_hit | tool_calls | duration |
|---------|---------|----------------|------------|------------|----------|
| fact_loop_max_turns | ✅ | 0 | n/a | 3 | 12.1s |
| fact_manager_methods | ✅ | 0 | n/a | 3 | 7.8s |
| history_loop_config | ✅ | 0 | 1 | 0 | 5.9s |
| history_manager_class | ✅ | 0 | 1 | 0 | 17.2s |
| edit_main_function | ✅ | 0 | n/a | 3 | 8.9s |
| edit_config_update | ✅ | 1 | n/a | 4 | 11.5s |
| recall_api_key | ✅ | 0 | 1 | 0 | 13.1s |
| recall_rate_limit | ✅ | 0 | 1 | 0 | 7.8s |
| dep_use_api_key | ❌ | 0 | n/a | 0 | 17.0s |
| dep_update_header | ✅ | 0 | 1 | 1 | 11.9s |
| multi_add_timeout | ✅ | 0 | 0 | 6 | 18.6s |
| multi_add_validation | ✅ | 0 | 0 | 4 | 23.5s |
| noise_db_config | ✅ | 0 | 0 | 2 | 10.1s |
| noise_cache_port | ✅ | 0 | 0 | 2 | 10.8s |

### memory_irrelevant

| task_id | correct | repeated_reads | memory_hit | tool_calls | duration |
|---------|---------|----------------|------------|------------|----------|
| fact_loop_max_turns | ✅ | 0 | n/a | 4 | 7.7s |
| fact_manager_methods | ✅ | 0 | n/a | 4 | 8.2s |
| history_loop_config | ✅ | 0 | 1 | 0 | 9.4s |
| history_manager_class | ✅ | 0 | 1 | 0 | 19.6s |
| edit_main_function | ✅ | 0 | n/a | 3 | 9.2s |
| edit_config_update | ✅ | 1 | n/a | 5 | 14.4s |
| recall_api_key | ✅ | 0 | 1 | 0 | 9.0s |
| recall_rate_limit | ✅ | 0 | 1 | 0 | 9.2s |
| dep_use_api_key | ✅ | 0 | 0 | 3 | 12.8s |
| dep_update_header | ✅ | 0 | 0 | 2 | 14.9s |
| multi_add_timeout | ✅ | 0 | 0 | 6 | 24.4s |
| multi_add_validation | ✅ | 0 | 1 | 2 | 17.6s |
| noise_db_config | ✅ | 0 | 0 | 1 | 6.4s |
| noise_cache_port | ✅ | 0 | 0 | 1 | 7.0s |
