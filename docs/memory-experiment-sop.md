# 记忆系统量化实验 SOP

> 版本: v1.0 | 创建: 2026-07-04 | 关联: P2 Memory Experiment

## 目标

产出一套可写进简历/文档的记忆系统量化结果，确保结论可复现、低波动、可解释。

## 一、实验前冻结

1. **冻结代码版本** — 记录 git commit id，实验期间不改代码。
2. **冻结模型配置** — 固定 `MIMO_MODEL`、`base_url`、温度相关配置（如果有）。
3. **冻结任务集** — 固定当前 `MEMORY_TASKS` 的内容、顺序、fixture。
4. **冻结实验脚本** — 固定 `memory_experiment.py` 版本，不边测边改。
5. **冻结运行环境** — 固定 workspace、依赖版本、API key 来源、网络条件尽量一致。

## 二、实验分组

统一跑 3 组：

| 配置 | 定义 |
|------|------|
| `memory_on` | 启用真实记忆注入 |
| `memory_off` | 关闭记忆注入 |
| `memory_irrelevant` | 启用记忆，但注入无关噪声记忆 |

定义不再改动。

## 三、实验轮次

- **最低标准**：每组 5 轮
- **推荐标准**：每组 7-10 轮
- **成本有限**：先跑 5 轮，若波动仍大再补到 7 轮

## 四、任务集要求

- 只使用正式任务集，不临时加减。
- 当前口径：14 个任务，7 类场景。
- **要求**：
  - 尽量包含必须依赖记忆的任务
  - 减少"不用记忆也能蒙对"的任务
  - verifier 必须尽量硬

## 五、每轮必须记录的字段

每个 config 每轮记录：

```
correct_rate
repeated_reads
memory_hit_rate
avg_tool_calls
avg_duration
eligible_memory_tasks
```

新增诊断字段：

```
was_truncated
sections.prefix.was_truncated
sections.tools.was_truncated
sections.memory.was_truncated
sections.history.was_truncated
```

如果能记录均值更好：

```
sections.*.raw_tokens
sections.*.rendered_tokens
```

## 六、每个任务级别建议记录

为便于排查波动，每个 task 最好额外记录：

```
task_id
category
correct
tool_calls
duration
repeated_reads
memory_hit
had_truncation
failed_reason（如果能归因）
```

## 七、执行顺序

每一轮固定顺序：`memory_on` → `memory_off` → `memory_irrelevant`。

每组之间加固定延迟，避免 429 和短时服务波动。如果已有延迟机制，继续保持一致。

## 八、实验中止条件

出现以下情况，本轮标记异常，不纳入正式统计：

- 明确 API 429 / 网络错误
- 模型服务异常返回
- 脚本崩溃
- 非任务逻辑导致的外部失败

**注意**：任务答错不算异常。模型工具选择失误属于有效结果，应保留。

## 九、结果汇总方式

不要只看单轮，统一按多轮汇总。对每个 config 计算：

| 统计量 | 说明 |
|--------|------|
| mean | 平均值 |
| min | 最小值 |
| max | 最大值 |
| range | max - min |
| std | 标准差（更严格时计算） |

## 十、可写入简历/文档的判定标准

只有满足下面条件，效果型数字才可写：

1. 跑满至少 5 轮
2. `memory_on` 平均结果持续优于 `memory_off`
3. 收益幅度大于波动幅度
4. 趋势方向一致，不出现明显反转
5. 没有依赖大量截断或异常轮次撑出来的结果

**实用阈值建议**：

- `correct_rate` 提升至少 **8-10 个百分点**，才值得主写
- `repeated_reads` 下降趋势要稳定，不能一会儿升一会儿降
- 若 `memory_irrelevant` 结果方向不稳定，不写它的收益/伤害数字，只写"三组对照体系已建立"

## 十一、哪些数字可以写

### 始终可写

- 14 个任务
- 7 类场景
- 800+ tests passed（记录 commit id 对应的具体数字）
- 建立 `memory_on/off/irrelevant` 三组真实对照评测体系

### 满足稳定标准后才写

- `memory_on` correct_rate 较 `memory_off` 提升 X 个百分点
- repeated_reads 降低 X%
- avg_tool_calls 或 avg_duration 优化 X%

### 谨慎使用，不建议主打

- `memory_hit_rate`

## 十二、结果异常时的处理

如果出现这类情况：

- `memory_on` 波动很大
- `memory_irrelevant` 反而更好
- 不同轮趋势反复反转

**处理原则**：

1. 不写效果结论
2. 只写机制与评测体系
3. 把异常记录进内部复盘文档
4. 必要时回头优化任务集和 verifier

## 十三、最终产出模板

实验结束后至少产出 2 份东西：

### 1. 正式实验报告

包含：
- commit id
- 模型版本
- 任务集版本
- 实验轮次
- 三组 mean/min/max
- 关键异常说明
- 最终可对外结论

### 2. 简历口径摘要

只保留：
- 能稳定复现的数字
- 1 句机制描述
- 1 句结果描述

## 十四、推荐执行节奏

1. 冻结当前版本
2. 跑 5 轮正式实验
3. 汇总 mean/min/max
4. 判断是否达到"可写阈值"
5. 达到 → 更新简历/面试稿
6. 未达到 → 只保留机制性成果，不写收益数字
