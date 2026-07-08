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
| memory_on | 100% | 100% (4/4) | 0% | 100% | 1.2 | 18.3s | ✅ 正常 |

## 正式结论（只看 clean rounds）

**以下结论只基于无异常任务的轮次：**

### memory_on
- correct_rate: 100%
- **memory_dependent_success_rate: 100%**（L3/L4 任务 4/4）
- target_reread_rate: 0%
- answer_without_reread_rate: 100%

## 各任务详情（按 L1-L4 分组）

### L4 任务（5 个）

#### memory_on

| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |
|---------|----------|---------|----------------|------------|------------|----------|---------------|

### L3 任务（5 个）

#### memory_on

| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |
|---------|----------|---------|----------------|------------|------------|----------|---------------|
| recall_api_key | cross_round_recall | ✅ | 0 | 1 | 0 | 21.1s |  |
| recall_rate_limit | cross_round_recall | ✅ | 0 | 1 | 0 | 11.7s |  |
| dep_use_api_key | cross_file_dep | ✅ | 0 | 0 | 3 | 21.1s |  |
| dep_update_header | cross_file_dep | ✅ | 0 | 0 | 2 | 19.4s |  |

### L2 任务（7 个）

#### memory_on

| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |
|---------|----------|---------|----------------|------------|------------|----------|---------------|

### L1 任务（1 个）

#### memory_on

| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |
|---------|----------|---------|----------------|------------|------------|----------|---------------|
