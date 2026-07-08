## Context

Phase 3.2A/3.2B 后，项目有 baseline runner 和 Memory v2，但评测体系无法区分 memory_on/memory_off 的行为差异。根因有两个：

1. **默认 baseline 走 mock 路径** — `_run_mock_task()` 直接返回常量，没有真实 agent 行为
2. **setup_turns 信息留在同一上下文里** — `clear_tool_history()` 只清统计，不清消息历史

## Goals / Non-Goals

**Goals:**
- 让默认 memory evaluation 走真实 agent loop（FakeModelClient 驱动）
- 设计对 memory 敏感的任务集（信息真正消失或检索昂贵）
- 建立适合 before/after 对比的 runner 和报告
- 调整指标体系，主效果指标从 correct_rate 切换到效率指标
- 为后续 Phase 3.2C Reflection 提供可信基线

**Non-Goals:**
- 不改 AgentLoop 核心逻辑
- 不改 Memory v2 架构
- 不做 real-model 大规模 benchmark（可选 small selective eval）
- 不做 Reflection / Hermes Curator

## Decisions

### D1：如何解决 mock 路径问题

**选择：用 FakeModelClient 驱动真实 AgentLoop**

当前 `_run_mock_task()` 跳过了整个 AgentLoop，直接返回常量。改造为：
- `use_real_model=False` 时，用 FakeModelClient 构建 AgentLoop
- FakeModelClient 提供确定性的 tool_call 序列
- 真实执行 tool（file_read、file_write、bash 等）
- 真实验证结果

**为什么不继续用 mock：**
- mock 路径不执行真实 tool，无法测量 tool_calls、duration 等效率指标
- mock 路径的 memory_hits 是机械赋值，不是真实行为

**为什么不直接用真实模型：**
- 真实模型有随机性，结果不可复现
- 真实模型需要 API key，不适合默认本地运行
- FakeModelClient 可以提供确定性 + 真实执行的组合

**风险：FakeModelClient 的行为可能太"完美"，无法体现 memory 带来的效率差异。**
- 缓解：如果 FakeModelClient + 新任务仍无差异，升级条件触发，real-model selective eval 变为必须项
- 兜底：如果现有 FakeModelClient 输出格式不足以稳定驱动所需 tool trajectory，则新增专用 scripted eval client 或测试适配层，而不是退回 `_run_mock_task()` 或弱化 benchmark 目标

### D2：如何解决 setup_turns 上下文残留问题

**选择：分层处理 — cross-session 任务优先，within-session 任务设计为"检索昂贵"**

**对于 cross-session recall 任务（最高优先级）：**
- setup 信息在另一个 session 文件中，不在当前 messages 里
- 信息真正"消失"，memory 是唯一获取途径
- 这是最干净的 memory-sensitive 场景

**对于 within-session 任务（episodic_notes、project_facts）：**
- 不修改 AgentLoop 的消息清理逻辑（影响太大）
- 设计为"从上下文查找很昂贵"：
  - 信息分散在多个 setup_turns 里
  - 主任务需要组合多条信息
  - reread 路径很长，memory 路径很短
- 用效率指标（tool_calls 差异）而非正确率指标来衡量

**为什么不直接清消息历史：**
- 改 AgentLoop 的消息管理逻辑影响面太大
- 可能破坏其他功能（conversation continuity、context compression）
- 在这个阶段不值得冒这个风险

### D3：指标体系调整

**选择：correct_rate 降级为 guardrail，效率指标升级为主效果指标**

| 定位 | 指标 | 说明 |
|------|------|------|
| 主效果指标 | avg_tool_calls | memory 价值 = 少读文件、少走弯路 |
| 主效果指标 | target_reread_rate | 有 memory 时是否减少了不必要的 reread |
| 主效果指标 | answer_without_reread_rate | cross-session 任务中，能否不 reread 就回答 |
| 主效果指标 | memory_dependent_success_rate | L3/L4 高依赖任务的成功率 |
| 辅助 guardrail | correct_rate | 不能因为追求效率牺牲正确性 |
| 诊断指标 | memory_hit_rate | 只用于诊断，不作为结论依据 |

**为什么调整：**
- 如果模型本身足够强，correct_rate 会长期接近满分
- memory 的价值更像"效率增强器"，不一定是"正确率增强器"
- 测试"有没有更省"、"有没有更稳"比"有没有答对"更有意义

**answer_without_reread_rate 的注意事项：**
- 对 cross-session 任务：这个指标是真实的（信息不在上下文里）
- 对 within-session 任务：这个指标需要谨慎解读（信息可能在 messages 里）
- 报告里要区分这两类任务

### D4：任务设计策略

**选择：新增 4-6 个任务，优先 cross-session recall**

**第一优先级：cross-session recall（至少 2 个）**
- 信息在另一个 session 文件中
- 主任务无法从当前 messages 获取
- memory 是唯一途径
- 设计方式：setup_turns 写入一个 session 文件，main_turn 通过 SessionSearch 检索

**第二优先级：episodic_notes 组合型（1-2 个）**
- setup 中分散给多条线索
- main turn 需要组合线索
- reread 路径长（需要读多个文件），memory 路径短（直接从 notes 获取）

**第三优先级：project_facts（1 个）**
- 必须是"不能从 repo 静态推断"的事实
- 比如私有 endpoint、内部约定、隐含规则
- 不能只是"pytest / uv"这种太容易猜到的事实

**不做：**
- user_preferences（太容易被模型猜到，除非是反直觉偏好）
- setup 把答案明说、main turn 再问一次的任务
- 只靠"有没有 reread"推断 memory 有效的任务

### D5：runner 架构

**选择：新建专用 memory eval runner，保留 baseline runner**

```
scripts/
├── run_phase32_baseline.py      # 保留，Phase 3.2A 宽快照入口
└── run_phase32_memory_eval.py   # 新增，memory-sensitive benchmark
```

**为什么新建而不是扩展：**
- baseline runner 继续作为"宽快照"（memory + recovery + permission）
- memory eval runner 专注"memory 敏感评测"
- 职责分离，避免一个 runner 越来越混

**memory eval runner 输出：**
- 三组对比：memory_on / memory_off / memory_irlevant
- 所有指标（主效果 + guardrail + 诊断）
- 报告区分主效果指标和诊断指标
- 如果 correct_rate 仍饱和，诚实写出

### D6：real-model selective eval 的定位

**选择：可选，但带升级条件**

默认不实现。升级条件：
> 如果 FakeModelClient + 真实 loop + 新任务仍无明显区分度，则 real-model selective eval 升级为必须项。

如果实现：
- 环境门控：`RUN_REAL_MEMORY_EVAL=1` + `MIMO_API_KEY`
- 只选 2-5 个最有区分度的任务
- 输出单独的 markdown / json
- 默认本地运行不依赖真实 key

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|------|------|------|
| FakeModelClient 行为太完美，效率指标也无差异 | 无法证明 memory 有价值 | 升级条件：触发 real-model eval |
| 新任务设计不当，仍然不敏感 | 浪费时间，结果不可信 | 先用现有任务跑真实 loop 分析，再有针对性设计 |
| cross-session 任务需要构建 session fixture | 增加测试复杂度 | 只做 2-3 个，不铺开 |
| 指标调整后，旧报告不可比 | 历史数据浪费 | 保留旧指标作为参考，新指标作为主结论 |
| FakeModelClient 的 tool_call 模式固定 | 可能无法体现"犹豫→纠正"等真实行为 | 这是 FakeModelClient 的固有限制，接受它 |
