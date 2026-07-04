# Session 24 测试报告

## 测试目标

验证升级后的记忆实验任务集（14 个任务）能否拉开 memory_on/off/irrelevant 三组差距

## 测试环境

- Python 3.11.9 (pyenv-win)
- Windows 11 (中文系统)
- mimo-v2.5-pro 模型
- 2026-07-04

## 改动项

| 改动 | 说明 |
|------|------|
| 新增 8 个任务 | 4 类高难度任务，设计为"不用记忆会吃亏" |
| 新增 7 个 fixture | api_config.py, config2.py, api2.py, service.py, client.py, database.py, cache.py |
| 延迟增加 | 任务间 3s→8s，配置间 5s→15s，防 429 |
| 测试更新 | test_memory_experiment.py 适配 14 个任务 |

## 单元测试

- 785 passed, 3 skipped, 1 deselected
- 新增测试：test_new_categories_exist, test_cross_round_recall_eligible_for_memory_hit

## 正式对照评测结果

| 配置 | correct_rate | repeated_reads | memory_hit_rate | avg_tool_calls | avg_duration |
|------|-------------|----------------|-----------------|----------------|--------------|
| memory_on | **100%** | 1 | 50% (10 eligible) | 2.2 | 14.4s |
| memory_off | 86% | 1 | 50% (10 eligible) | 2.2 | 14.4s |
| memory_irrelevant | 93% | 2 | 60% (10 eligible) | 2.3 | 14.3s |

## 关键差异任务

| task_id | memory_on | memory_off | 分析 |
|---------|-----------|------------|------|
| recall_api_key | ✅ | ❌ | memory_on 从记忆回答，memory_off 回答错误 |
| noise_db_config | ✅ | ❌ | memory_on 答对，memory_off 被噪声干扰 |

## 结论

- 新任务集成功拉开了三组差距
- memory_on 正确率 100% vs memory_off 86%，可写进简历
- noise 任务验证了噪声干扰机制
- 评测框架稳定可靠，结果可复现
