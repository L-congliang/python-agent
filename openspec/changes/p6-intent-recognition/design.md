## Context

当前 System Prompt 由 `_build_system_prompt()` 在 `loop.py:820` 中组装，结构为：
1. config.system_prompt（用户传入，可能为空）
2. config.append_system_prompt（追加，可能为空）
3. memory.render()（工作记忆 + 文件摘要 + 事件笔记）
4. 工具列表（一行一个，只写 name + description）
5. SubAgent 使用指南（硬编码）

问题：
- 没有身份定义，模型不知道自己是什么
- 没有行为准则，模型行为方差大
- 工具描述孤立，模型需要自己推理工具选择策略
- 没有 Plan Mode，复杂任务不规划直接执行

约束：
- 不改变 AgentLoop 核心循环逻辑
- 不引入新依赖
- 代码质量标准：mypy --strict、测试覆盖
- 面向面试：每个设计决策要能讲清楚"为什么"

## Goals / Non-Goals

**Goals:**
- 优化 System Prompt 结构，提升模型工具选择准确率
- 实现 Plan Mode，支持"先规划后执行"的工作流
- 通过 Prompt Ablation Experiment 验证优化效果
- 保持 benchmark pass_rate 不退化

**Non-Goals:**
- 不做显式意图分类器（纯 prompt 引导足够，实验数据验证）
- 不做自动触发 Plan Mode（用户触发更可控）
- 不做严格的计划格式（纯文本 markdown 足够）
- 不改 Tool Protocol 架构

## Decisions

### D1: System Prompt 结构 — 四块式组装

**选择：** Identity + Behavioral Guidelines + Tool Selection Guide + Dynamic Context

**替代方案：**
- A) 保持现状（只拼接 config + memory + 工具列表）— 信息不足，模型行为不稳定
- B) 写一个超长完整 prompt（2000+ token）— token 成本高，Lost in the Middle 风险

**理由：** 四块式结构每块有明确职责，总长度控制在 500-800 token。Identity 定义角色，Behavior 收窄行为空间，Tool Guide 引导工具选择，Dynamic Context 提供实时信息。

### D2: 行为准则 — 通用原则 + 具体规则

**选择：** 3-4 条通用原则 + 3-5 条高频场景的具体规则

**替代方案：**
- A) 只写通用原则（"先理解再动手"）— 模型可能理解偏差
- B) 只写具体规则（"改文件前必须先读"）— 覆盖不全

**理由：** 通用原则收窄高层行为空间（覆盖所有类似场景），具体规则约束高频操作（精度高）。两者互补。依据：Claude Code 的 system prompt 也采用"原则 + 规则"结构，即使是顶级模型也需要显式指令来降低输出方差。

### D3: Tool Selection Guide — 集中管理

**选择：** 在 system prompt 里写一段工具选择指南（约 200 token），不在每个工具 description 里分散写

**替代方案：**
- A) 在每个工具 description 里加选择提示 — 分散，难维护
- B) 不加指南，靠模型自己推理 — mimo 推理能力不足以稳定选对

**理由：** 集中管理更清晰，信息密度高，且不重复。Claude Code 也是在 system prompt 里集中写工具使用规则。

### D4: Tool Description — 微调不重写

**选择：** 只在关键工具 description 加一句选择提示

**替代方案：**
- A) 不改 description — system prompt 里的指南可能不够
- B) 大改 description（加详细用法、示例）— 和 system prompt 重复，且 description 太长影响工具列表渲染

**理由：** 微调最小化改动，只加最关键的提示。edit 加"优先于 write 使用"，grep 加"优先于 bash grep"。

### D5: Plan Mode — 用户触发 + 权限控制

**选择：** 用户通过 system prompt 引导触发，PermissionChecker 切换 mode 控制工具可用性

**替代方案：**
- A) 纯 prompt 引导（不加权限控制）— 模型可能"越狱"直接执行
- B) 纯权限控制（不加 prompt 引导）— 模型不理解为什么被拒绝，可能反复尝试

**理由：** prompt 引导让模型理解当前是规划阶段，权限兜底防止误操作。两层防护。Plan Mode 期间允许只读工具（read, grep, glob, bash 只读命令），禁止写操作（write, edit, bash 写命令）。

### D6: Plan Mode 触发 — 用户手动

**选择：** 用户说"先规划"或类似意图时，system prompt 引导模型输出计划

**替代方案：**
- A) 自动触发（检测复杂任务）— 规则难定，判断错了体验差
- B) 命令触发（/plan）— 需要改 CLI，增加复杂度

**理由：** 用户最清楚要不要规划。Claude Code 也是用户手动触发（Enter 键切换）。自动触发可以作为后续优化。

### D7: 计划格式 — 纯文本 markdown

**选择：** 模型输出纯文本 markdown 计划，不定义严格格式

**替代方案：**
- A) JSON 格式 — 模型输出 JSON 容易出错（mimo 的 JSON 遵循能力一般），用户看不懂
- B) 特定标记格式（如 `## PLAN_START` ... `## PLAN_END`）— 增加解析复杂度，收益不大

**理由：** 纯文本 markdown 最自然，模型输出稳定，用户直接看懂。用户确认后切换到执行模式。

### D8: Prompt Ablation Experiment — 对比 4 个配置

**选择：** 对比 baseline / +identity / +tool_guide / +full 四个配置的工具选择准确率

**替代方案：**
- A) 只对比 baseline vs full — 不知道哪个模块贡献最大
- B) 对比更多配置（加行为准则、加微调 description 等）— 实验太复杂

**理由：** 4 个配置足够定位效果来源。identity 和 tool_guide 是两个核心改动，分开对比能知道各自贡献。

## Risks / Trade-offs

**[Risk] Prompt 太长导致 token 成本增加**
→ Mitigation: 控制总长度在 500-800 token，约增加 300 token/次调用。按 128K 窗口算，占比 <1%。

**[Risk] mimo 不遵循行为准则**
→ Mitigation: Prompt Ablation Experiment 验证。如果准确率没提升，调整准则措辞或简化。

**[Risk] Plan Mode 被模型忽略**
→ Mitigation: 权限兜底——即使模型尝试写操作也会被拦截，返回错误信息引导模型输出计划。

**[Risk] Tool Selection Guide 和 Tool Description 信息冲突**
→ Mitigation: Guide 是高层策略（"用什么"），Description 是低层细节（"怎么用"），不冲突。
