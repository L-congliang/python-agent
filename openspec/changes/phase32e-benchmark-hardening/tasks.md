## Phase 3.2E: Benchmark Hardening - Realistic Memory Evaluation

### 任务卡 1：清理 baseline 口径与真实产物一致性

**目标：** 消除认知债务，让文档、脚本、产物三者一致。

**重点文件：**
- `docs/agent-improvement/13-phase3.2-eval-baseline.md`
- `docs/agent-improvement/14-phase3.2b-memory-v2.md`
- `docs/agent-improvement/04-testing-record.md`

**要做的事：**
- [ ] 明确写出：当前 baseline 默认 memory 指标来自 mock 路径，不是完整真实执行
- [ ] 删除或重写所有会让读者误以为当前真实结果是 0.85 vs 0.75 的示例
- [ ] 让文档 schema 和代码实际输出字段一致（当前代码输出 7 个指标，文档只写了 3 个）
- [ ] 明确写出当前真实现状：
  - correct_rate 饱和
  - memory_hit_rate 有差异但反转
  - 当前 taskset / eval 设计不足以支撑强结论
- [ ] memory_irrelevant 纳入说明，不能"代码里有，报告里看不见"

**验收标准：**
- [ ] 文档不再夸大当前量化结果
- [ ] 文档与实际 json / md 产物一致
- [ ] 读者能清楚区分"示例值"和"当前真实值"

---

### 任务卡 2：让 MemoryExperiment 脱离 mock 主路径，并重构任务设计

**目标：** 这是本阶段核心任务。解决两个根本问题：mock 路径 + 上下文残留。

**重点文件：**
- `src/agent/evaluation/memory_experiment.py`
- `tests/test_memory_experiment.py`
- `tests/test_memory_cross_session.py`
- `tests/fixtures/memory_experiment/`

#### 子任务 2.1：去 mock 化

**目标：** 让默认 memory evaluation 走 FakeModelClient + 真实 AgentLoop。

**要做的事：**
- [ ] 改造 `MemoryExperiment` 的 `use_real_model=False` 路径
- [ ] 用 FakeModelClient 构建真实 AgentLoop，而不是走 `_run_mock_task()`
- [ ] FakeModelClient 提供确定性的 tool_call 序列
- [ ] 真实执行 tool（file_read、file_write、bash 等）
- [ ] 真实测量 tool_calls、duration 等指标

**测试要求：**
- [ ] `tests/test_memory_experiment.py`：默认 eval 不再走纯 mock 常量主路径
- [ ] FakeModelClient 驱动的 loop 能产出真实的 tool_calls 和 duration

**验收标准：**
- [ ] `MemoryExperiment(use_real_model=False)` 不再调用 `_run_mock_task()`
- [ ] 默认 baseline 走真实 agent loop

#### 子任务 2.2：用现有任务跑真实 loop 分析

**目标：** 在设计新任务之前，先用 FakeModelClient + 真实 loop 跑现有 24 个任务，分析哪些已有区分度。

**要做的事：**
- [ ] 用改造后的 `MemoryExperiment` 跑现有 24 个任务
- [ ] 对比 memory_on / memory_off / memory_irrelevant 的指标
- [ ] 分析哪些任务"天然敏感"（tool_calls 有差异）
- [ ] 分析哪些任务"天然不敏感"（on/off 都一样）
- [ ] 记录分析结果，指导 2.3 的任务设计

**产出：**
- [ ] 分析报告（可以是文档或注释），说明现有任务的敏感度分布

**验收标准：**
- [ ] 有数据支撑"哪些任务需要重新设计，哪些可以保留"

#### 子任务 2.3：重构任务设计

**目标：** 设计让 memory 真正必要或无 memory 路径明显更昂贵的任务。

**设计原则：**

**第一优先级：cross-session recall（至少 2 个）**
- 信息在另一个 session 文件中，不在当前 messages 里
- 信息真正"消失"，memory 是唯一获取途径
- 设计方式：setup_turns 写入一个 session 文件，main_turn 通过 SessionSearch 检索

**第二优先级：episodic_notes 组合型（1-2 个）**
- setup 中分散给多条线索
- main turn 需要组合线索
- reread 路径长（需要读多个文件），memory 路径短（直接从 notes 获取）

**第三优先级：project_facts（1 个）**
- 必须是"不能从 repo 静态推断"的事实
- 比如私有 endpoint、内部约定、隐含规则

**不要做的错误任务：**
- setup 把答案明说，main turn 再问一次
- 用户偏好等于通用 best practice
- 项目事实可直接从文件结构轻易看出
- 只靠"有没有 reread"推断 memory 真有效

**测试要求：**
- [ ] 新任务确实命中 cross-session recall
- [ ] memory_irrelevant 不会被误判为有益
- [ ] 新任务在 deterministic 路径下结果稳定
- [ ] 至少一个主效果指标能比当前更有区分度

**验收标准：**
- [ ] 新增 4-6 个任务，其中至少 2 个 cross-session recall
- [ ] 新任务不再依赖 setup 信息残留在同一上下文里就能轻松过
- [ ] 至少一个主效果指标比当前明显更敏感

#### 子任务 2.4：调整指标体系

**目标：** 主效果指标从 correct_rate 切换到效率指标。

**指标定位调整：**

| 定位 | 指标 | 说明 |
|------|------|------|
| 主效果指标 | avg_tool_calls | memory 价值 = 少读文件、少走弯路 |
| 主效果指标 | target_reread_rate | 有 memory 时是否减少了不必要的 reread |
| 主效果指标 | answer_without_reread_rate | cross-session 任务中，能否不 reread 就回答 |
| 主效果指标 | memory_dependent_success_rate | L3/L4 高依赖任务的成功率 |
| 辅助 guardrail | correct_rate | 不能因为追求效率牺牲正确性 |
| 诊断指标 | memory_hit_rate | 只用于诊断，不作为结论依据 |

**注意事项：**
- `answer_without_reread_rate` 对 cross-session 任务是真实的，对 within-session 任务需谨慎解读
- 报告里要区分这两类任务的该指标

**验收标准：**
- [ ] MemoryMetrics 的指标定位已调整
- [ ] 报告格式区分主效果指标和诊断指标
- [ ] memory_hit_rate 不再作为结论依据

---

### 任务卡 3：新建 memory eval runner

**目标：** 有了敏感任务之后，把 runner 做成可复跑、可读、可比较。

**建议新增文件：**
- `scripts/run_phase32_memory_eval.py`
- 可选：`tests/test_memory_eval_runner.py`

**保留：**
- `scripts/run_phase32_baseline.py`（继续作为 Phase 3.2A 宽快照入口）

**runner 输出要求：**
- [ ] 三组对比：memory_on / memory_off / memory_irrelevant
- [ ] 所有指标（主效果 + guardrail + 诊断）
- [ ] JSON 输出 + Markdown 报告

**报告要求：**
- [ ] 明确主效果指标是什么
- [ ] 哪些只是诊断指标
- [ ] memory_irrelevant 为什么存在
- [ ] 当前差异体现在哪
- [ ] 如果 correct_rate 仍接近饱和，诚实写出
- [ ] 不能为了好看强行包装出"显著提升"

**测试要求：**
- [ ] 输出 json + md
- [ ] memory_irrelevant 被纳入正式输出
- [ ] 结果来自真实执行路径，不是硬编码漂亮数值
- [ ] schema 稳定

**验收标准：**
- [ ] 有一个真正适合 before / after 的 memory eval runner
- [ ] runner 不只是"打印一堆 1.0"
- [ ] 报告能解释结果，而不是只打印表格

---

### 任务卡 4：可选 env-gated selective real-model eval

**目标：** 只作为补充验证，不是本阶段核心。带升级条件。

**升级条件：**
> 如果 FakeModelClient + 真实 loop + 新任务仍无明显区分度，则 real-model selective eval 升级为必须项。

**建议新增文件：**
- `scripts/run_real_memory_eval.py`
- `tests/test_real_memory_eval_smoke.py`

**环境门控：**
- `RUN_REAL_MEMORY_EVAL=1`
- `MIMO_API_KEY`

**设计要求：**
- [ ] 使用任务卡 2 里新设计的敏感任务，不要拿旧任务换个模型再跑一遍
- [ ] 只选 2-5 个最有区分度的任务
- [ ] 输出单独的 markdown / json

**验收标准：**
- [ ] 默认本地测试不依赖真实 key
- [ ] 开启 env 后，能跑 selective real-model eval
- [ ] 文档明确区分 fake deterministic eval 与 real-model selective eval

---

### 任务卡 5：文档与量化结论固化

**目标：** 把"我们到底解决了什么评测问题"讲清楚。

**重点文件：**
- `docs/agent-improvement/04-testing-record.md`
- `docs/agent-improvement/07-next-roadmap.md`
- `docs/agent-improvement/14-phase3.2b-memory-v2.md`
- 新增：`docs/agent-improvement/15-phase3.2e-benchmark-hardening.md`

**必须写清的结论：**
- [ ] 之前为什么"评测很多但不满意"
  - mock 路径问题
  - setup_turns 残留上下文问题
- [ ] 现在主效果指标已经从"只盯 correct_rate"调整为"效率 + 高依赖成功率"
- [ ] 为什么这一步做完后，Phase 3.2C Reflection 才值得继续
- [ ] 后续建议项：real-model selective eval（如果本阶段未实现）

**验收标准：**
- [ ] 文档能让外部读者理解：旧评测为什么不够
- [ ] 新评测到底改进了什么
- [ ] 为什么先做 benchmark hardening 再做 reflection

---

## 执行顺序

```
Phase 1: 清理认知债务
└─ 任务卡 1: 先清文档口径

Phase 2: 核心改造
└─ 任务卡 2: 先改 execution path + task design
   ├─ 2.1 去 mock 化
   ├─ 2.2 用现有任务跑真实 loop 分析
   ├─ 2.3 再重构任务（重点 cross-session）
   └─ 2.4 最后调指标体系

Phase 3: 基础设施
└─ 任务卡 3: 新建 memory eval runner

Phase 4: 可选补充
└─ 任务卡 4: real-model selective eval（带升级条件）

Phase 5: 收尾
└─ 任务卡 5: 统一固化文档和量化结论
```

## 建议先写哪些测试

1. `tests/test_memory_experiment.py` — 验证去 mock 化 + 新任务
2. `tests/test_memory_cross_session.py` — 验证 cross-session 任务
3. `tests/test_evaluation_baseline_runner.py` — 验证 runner 输出
4. `tests/test_real_memory_eval_smoke.py`（可选）— 验证 real-model eval

## 建议运行命令

```bash
# 核心测试
uv run pytest tests/test_memory_experiment.py -q
uv run pytest tests/test_memory_cross_session.py -q
uv run pytest tests/test_evaluation_baseline_runner.py -q

# 全量测试
uv run pytest tests -q

# baseline runner（保持可用）
uv run python scripts/run_phase32_baseline.py

# 新 memory eval runner
uv run python scripts/run_phase32_memory_eval.py

# real-model selective eval（可选）
RUN_REAL_MEMORY_EVAL=1 MIMO_API_KEY=... uv run python scripts/run_real_memory_eval.py
```

## 审核标准

我会重点查这些：
- [ ] 是否还在默认主路径上依赖 `_run_mock_task()`
- [ ] 是否通过 cross-session 优先 + within-session 昂贵检索设计，规避了 setup_turns 残留导致的主要评测失真
- [ ] 是否只是"换了更难任务"，但信息依然没真正消失
- [ ] 是否把主效果指标从单一 correct_rate 调整到了更合理的效率指标
- [ ] 是否把 memory_irrelevant 纳入正式解释
- [ ] 是否把 real-model eval 放在了正确优先级上（可选，但带升级条件）
- [ ] 全量测试是否继续为绿

## 不通过的情况

- 只改文档，不改 taskset / runner
- 继续拿 memory_hit_rate 当唯一主结论
- 把示例数值写成真实当前结果
- 只加了一个 real-model smoke，却没有补足 fake benchmark 的敏感度问题
- 把 3.2E 做成又一轮"链路打通"，但仍然不能回答 Memory v2 有没有效果
- 一上来就顺手做 3.2C Reflection
