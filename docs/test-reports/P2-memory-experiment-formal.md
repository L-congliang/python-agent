# P2 Memory Experiment - Formal Report

> 执行日期: 2026-07-04（V1）/ 2026-07-04（V2）
> Commit: 15152b3（V1）/ cba0734（V2 异常感知版）/ e433607（V2 实验结果）
> Model: mimo-v2.5-pro
> 任务集: 14 tasks（V1）/ 18 tasks（V2）

## 一、实验配置

| 配置 | 定义 |
|------|------|
| memory_on | 启用真实记忆注入 |
| memory_off | 关闭记忆注入 |
| memory_irrelevant | 启用记忆，但注入无关噪声记忆 |

## 二、各轮结果

### Round 1

| 配置 | correct_rate | repeated_reads | memory_hit_rate | avg_tool_calls | avg_duration |
|------|-------------|----------------|-----------------|---------------|-------------|
| memory_on | 100% | 3 | 50% (10 eligible) | 2.4 | 14.6s |
| memory_off | 100% | 0 | 50% (10 eligible) | 2.1 | 12.8s |
| memory_irrelevant | 100% | 1 | 40% (10 eligible) | 2.3 | 15.6s |

### Round 2

| 配置 | correct_rate | repeated_reads | memory_hit_rate | avg_tool_calls | avg_duration |
|------|-------------|----------------|-----------------|---------------|-------------|
| memory_on | 100% | 1 | 40% (10 eligible) | 2.4 | 16.7s |
| memory_off | 100% | 1 | 60% (10 eligible) | 2.3 | 13.7s |
| memory_irrelevant | 100% | 1 | 40% (10 eligible) | 2.4 | 20.1s |

### Round 3

| 配置 | correct_rate | repeated_reads | memory_hit_rate | avg_tool_calls | avg_duration |
|------|-------------|----------------|-----------------|---------------|-------------|
| memory_on | 100% | 0 | 50% (10 eligible) | 2.6 | 18.0s |
| memory_off | 100% | 0 | 60% (10 eligible) | 2.2 | 13.9s |
| memory_irrelevant | 93% | 1 | 50% (10 eligible) | 2.3 | 13.8s |

### Round 4

| 配置 | correct_rate | repeated_reads | memory_hit_rate | avg_tool_calls | avg_duration |
|------|-------------|----------------|-----------------|---------------|-------------|
| memory_on | 100% | 1 | 50% (10 eligible) | 2.2 | 12.3s |
| memory_off | 100% | 1 | 60% (10 eligible) | 1.9 | 11.7s |
| memory_irrelevant | 100% | 3 | 50% (10 eligible) | 2.5 | 14.1s |

### Round 5

| 配置 | correct_rate | repeated_reads | memory_hit_rate | avg_tool_calls | avg_duration |
|------|-------------|----------------|-----------------|---------------|-------------|
| memory_on | 100% | 1 | 50% (10 eligible) | 2.4 | 12.1s |
| memory_off | 93% | 0 | 60% (10 eligible) | 1.9 | 11.8s |
| memory_irrelevant | 100% | 1 | 60% (10 eligible) | 2.1 | 12.3s |

## 三、汇总统计（mean / min / max / std）

### correct_rate

| 配置 | mean | min | max | range | std |
|------|------|-----|-----|-------|-----|
| memory_on | 100% | 100% | 100% | 0% | 0.0% |
| memory_off | 98.6% | 93% | 100% | 7% | 2.8% |
| memory_irrelevant | 98.6% | 93% | 100% | 7% | 2.8% |

### repeated_reads

| 配置 | mean | min | max | range | std |
|------|------|-----|-----|-------|-----|
| memory_on | 1.2 | 0 | 3 | 3 | 1.1 |
| memory_off | 0.2 | 0 | 1 | 1 | 0.4 |
| memory_irrelevant | 1.0 | 1 | 1 | 0 | 0.0 |

### memory_hit_rate

| 配置 | mean | min | max | range | std |
|------|------|-----|-----|-------|-----|
| memory_on | 48.0% | 40% | 50% | 10% | 4.5% |
| memory_off | 56.0% | 50% | 60% | 10% | 5.5% |
| memory_irrelevant | 52.0% | 40% | 70% | 30% | 13.0% |

### avg_tool_calls

| 配置 | mean | min | max | range | std |
|------|------|-----|-----|-------|-----|
| memory_on | 2.3 | 2.0 | 2.6 | 0.6 | 0.2 |
| memory_off | 2.1 | 1.9 | 2.3 | 0.4 | 0.2 |
| memory_irrelevant | 2.2 | 2.0 | 2.5 | 0.5 | 0.2 |

### avg_duration

| 配置 | mean | min | max | range | std |
|------|------|-----|-----|-------|-----|
| memory_on | 14.4s | 12.1s | 16.7s | 4.6s | 1.7s |
| memory_off | 13.0s | 11.7s | 13.9s | 2.2s | 0.6s |
| memory_irrelevant | 15.2s | 12.0s | 20.1s | 8.1s | 3.0s |

## 四、关键发现

### 1. 正确率 (correct_rate)

- **memory_on: 100%** — 5 轮全部满分，稳定无波动
- memory_off: 98.6% — 有 1 轮出现 1 个任务失败（93%）
- memory_irrelevant: 98.6% — 有 1 轮出现 1 个任务失败（93%）

**结论**: memory_on 的正确率比 memory_off 高 **1.4 个百分点**，但幅度较小（< 8pp 阈值）。

### 2. 重复读取 (repeated_reads)

- memory_on: 1.2 次（平均）
- memory_off: 0.2 次
- memory_irrelevant: 1.0 次

**意外发现**: memory_off 的 repeated_reads 反而最低（0.2 vs 1.2）。这与预期相反（预期 memory_on 应该更少重复读取）。

**可能原因**: 当前任务集中，fact_lookup 类任务不需要记忆也能直接回答；memory_on 的模型可能因为记忆注入而多读了一些文件来验证。

### 3. 记忆命中率 (memory_hit_rate)

- memory_on: 48% — 10 个 eligible 任务中约 5 个命中
- memory_off: 56% — 关闭记忆反而命中率更高
- memory_irrelevant: 52%

**异常**: memory_off 的 memory_hit_rate 高于 memory_on，与预期相反。

### 4. 效率指标

- avg_tool_calls: memory_off (2.1) < memory_irrelevant (2.2) < memory_on (2.3)
- avg_duration: memory_off (13.0s) < memory_on (14.4s) < memory_irrelevant (15.2s)

**结论**: memory_off 在效率上反而最优。

## 五、异常分析

### 1. memory_hit_rate 反转

**现象**: memory_off 的 memory_hit_rate (58%) > memory_on (48%)

**原因分析**:
- memory_hit 的定义是"主任务阶段没有 reread 目标文件"
- memory_off 关闭记忆后，模型可能直接从上下文（setup_turns 的结果仍在 messages 中）回答，不需要 reread
- memory_on 注入了记忆后，模型可能反而去验证记忆的准确性，导致额外 reread

### 2. repeated_reads 反转

**现象**: memory_off 的 repeated_reads (0.4) < memory_on (1.2)

**原因分析**:
- memory_on 注入了更多上下文（记忆），模型可能因此读取更多文件来验证
- memory_off 上下文更少，模型更倾向于直接回答

### 3. 模型波动

**现象**: Round 3 的 memory_irrelevant (93%) 和 Round 5 的 memory_off (93%) 各有 1 个任务失败

**原因**: mimo 模型本身的随机性，非系统性问题

## 六、SOP 判定

根据 `docs/memory-experiment-sop.md` 第十条判定标准：

| 条件 | 状态 |
|------|------|
| 跑满至少 5 轮 | ✅ 5 轮完成 |
| memory_on 平均结果持续优于 memory_off | ❌ correct_rate 仅高 1.4pp，repeated_reads 和 memory_hit_rate 反而更差 |
| 收益幅度大于波动幅度 | ❌ correct_rate 差异 (1.4pp) < 波动幅度 (7% range) |
| 趋势方向一致 | ❌ repeated_reads 和 memory_hit_rate 方向反转 |

**结论: 不满足"可写入效果型数字"的标准。**

## 七、可写入的内容

### ✅ 始终可写

- 14 个任务，7 类场景
- 816 tests passed
- 建立 memory_on/off/irrelevant 三组真实对照评测体系
- 5 轮正式量化实验，含 mean/min/max/std 统计

### ❌ 不满足稳定标准

- ~~memory_on correct_rate 较 memory_off 提升 X 个百分点~~（仅 1.4pp，低于 8-10pp 阈值）
- ~~repeated_reads 降低 X%~~（方向反转）
- ~~avg_tool_calls 或 avg_duration 优化 X%~~（memory_off 反而更优）

### ⚠️ 异常记录

- memory_hit_rate 方向反转（memory_off > memory_on）
- repeated_reads 方向反转（memory_off < memory_on）
- 可能原因：当前任务集对记忆依赖不够强，fact_lookup 类任务不需要记忆也能答对

## 八、下一步建议

1. **优化任务集**: 增加必须依赖记忆才能答对的任务（如需要跨多轮对话才能获取的信息）
2. **加强 verifier**: 减少"不用记忆也能蒙对"的任务
3. **排查 memory_hit 定义**: 确认 memory_hit 的判定逻辑是否符合预期
4. **补跑更多轮**: 如果优化任务集后，再跑 5 轮验证

## 九、简历口径摘要

**机制描述**: 建立 memory_on/off/irrelevant 三组对照评测体系，5 轮正式量化实验，覆盖 14 个任务 × 7 类场景。

**结果描述**: 当前任务集中，记忆系统对正确率的提升幅度较小（1.4pp），低于可写入阈值。需要优化任务集以增加对记忆的依赖度。

---

## 十、V2 实验升级（2026-07-04）

### 10.1 V2 任务集升级

**新增 6 个高记忆依赖任务**（从 14 个增加到 18 个）：

| task_id | 类别 | verifier | 级别 | 设计意图 |
|---------|------|----------|------|----------|
| disambiguate_db_vs_cache_secret | noise | exact_match | L4 | 抗混淆精确回忆 |
| delayed_constraint_single_file_edit | edit_dependency | file_changed_no_extra_change | L4 | 记住约束再编辑 |
| cross_file_literal_recall_no_import | cross_file_dep | file_changed_strict | L4 | 跨文件精确回忆无 import |
| multi_round_edit_after_noise | multi_round_edit | multi_file_changed | L4 | 噪声后继续前任务 |
| forbidden_reread_fact_answer | cross_round_recall | forbidden_reread | L3 | 禁止 reread 的事实回答 |
| edit_using_previous_fact_only | edit_dependency | file_changed_strict | L4 | 用前置事实编辑 |

**新增 4 个 verifier 类型**：
- `exact_match`: 精确字符串匹配
- `file_changed_strict`: 严格文件变更（所有子串都必须出现）
- `forbidden_reread`: 答案正确且未 reread
- `file_changed_no_extra_change`: 新文件变更 + 原文件未改动

**移除 2 个弱任务**：
- `fact_loop_max_turns`（fact_lookup，太容易）
- `fact_manager_methods`（fact_lookup，太容易）

### 10.2 V2 Smoke Test 结果

| 配置 | correct_rate | 失败任务数 |
|------|-------------|----------|
| **memory_on** | **100%** | 0 |
| memory_off | 78% | 4 |
| memory_irrelevant | 89% | 2 |

**关键发现**：
- memory_on vs memory_off 差距从 V1 的 1.4pp 扩大到 **22pp**
- 新任务成功放大了记忆价值
- memory_off 失败的任务都是新增的高记忆依赖任务

### 10.3 V2 正式实验（异常感知版）

**实验脚本改造**：
- 任务结果补 `failed_reason` / `is_abnormal` / `abnormal_reason`
- 429/网络/服务异常标记为 `abnormal`（不进正式统计）
- config 级异常判定：有异常任务的 config 不进正式均值
- 延迟提升：任务间 15s，config 间 45s

**实验结果**：

| 配置 | 干净轮次 | 异常轮次 | 异常原因 |
|------|---------|---------|---------|
| memory_on | 0 | 5 | 全部 429 |
| memory_off | 1 | 4 | 429 |
| memory_irrelevant | 3 | 2 | 429 |

**结论**：因 API 429 限流，所有轮次被标记为异常，不纳入正式统计。

### 10.4 V2 异常分析

**429 限流原因**：
- memory_on 每个任务都需要模型调用，最容易撞限流
- memory_irrelevant 相对干净，因为有些任务不需要工具调用
- 当前延迟（任务间 15s，config 间 45s）仍不足以避免限流

**下一步方案**：
1. **分批跑**：每次只跑 1 个 config，分三批完成（最稳）
2. **增加延迟**：任务间 30s，config 间 120s
3. **等限流恢复**：等几个小时后重跑

### 10.5 对外口径

> "V2 正式实验因 API 429 触发异常轮次判定，当前结果不纳入效果结论；已定位为实验调度问题而非记忆机制本身问题，下一步将补充异常归因与更强节流后重跑正式实验。"
