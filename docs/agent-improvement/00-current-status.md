# 当前状态

更新时间：2026-07-08

## 当前定位

这个项目现在最合适的定位是：

`扎实的 Demo，接近 Prototype 边缘（核心能力闭环，评测体系可验证）`

关键区别：不只是"做了功能"，而是能用自建 benchmark 验证 agent 机制的收益来自哪里。

## Phase 3.1 复盘材料已沉淀

Phase 3.1 的源码理解笔记已沉淀到：
- `docs/agent-improvement/11-phase3.1-source-review.md`

包含：
- Phase 3.1 目标
- 源码阅读顺序
- 5 个关键问题与答案
- 面试可讲口径

不是：

- 生产级 Claude Code 替代品
- 完整 MCP 平台
- WebUI 产品
- 多 agent 并行系统

## 当前已经稳定落地的能力

### 基础能力（Phase 0-1）
- `AgentLoop / ToolRegistry / tools` 的多轮工具调用闭环
- 基础工具：`bash / read / write / edit / grep / glob`
- `ALLOW / ASK / DENY` 权限系统
- CLI confirmation handler
- `file_edit` diff preview
- `file_edit` 原子写入失败保护
- workspace guard
- 任务级 e2e regression
- 默认入口 smoke test
- 中文文档包、简历版材料、面试复习材料

### 上下文工程（Phase 2.2）
- **Observation Budget 契约**：工具输出的 preview + artifact 双层机制
- **统一截断逻辑**：bash/read/grep/glob/edit 的长输出统一处理
- **CLI 截断提示**：用户能看到"输出已截断，完整结果在 xxx"
- **artifact 落盘**：长输出自动保存到 .artifacts 目录
- **CLI 事件链路**：所有 tool_result 事件都能在默认 CLI 路径显示

### 可恢复能力（Phase 2.3A）
- **Backup / Rollback / Edit History**：write/edit 前自动备份
- **历史记录**：记录 tool_name、file_path、action、backup_path、before_hash、after_hash、preview
- **CLI 命令**：/history 和 /rollback latest
- **两种回退**：created（删除文件）、modified（恢复备份）

### 权限体验（Phase 2.3B）
- **Session 级 Permission Policy**：减少重复 ASK
- **allow-once / allow-session**：按精确 command 或规范化路径匹配
- **CLI 交互**：y=本次允许，a=本 session 允许，n/Enter=拒绝
- **安全边界**：DENY 不被 session allow 绕过，/reset 清空 session policy

### 真实远程链路（Phase 2.3C）
- **真实远程 LLM Smoke**：验证真实 API 链路没断
- **环境门控**：RUN_REAL_LLM_SMOKE=1，MIMO_API_KEY 缺失时自动 skip
- **收敛 prompt**：client 用"reply with exactly OK"，agent loop 用"read hello.txt"
- **错误区分**：网络/API 异常时，报错能区分是远程问题

### 记忆系统（Phase 3.2B）
- **分层记忆**：working memory / episodic notes / durable memory
- **Cross-session retrieval**：SessionSearch 搜索历史 session 文件
- **默认 loop 接入**：assemble_layered() 包含 cross-session recall

### 受控反思（Phase 3.2C）
- **ReflectionPolicy**：三个触发器（incorrect / reread / high_tool_calls）
- **ReflectionBuilder**：预算受控的反思 prompt 构造，输出 ReflectionPlan
- **Bounded one-shot retry**：每任务最多 1 次 reflection，不递归
- **PromptAwareScriptedModelClient**：根据 reflection prompt 内容选 retry branch

### 评测体系（Phase 3.2E/3.2F）
- **ScriptedModelClient 驱动真实 AgentLoop**：替代 mock 路径
- **Memory-sensitive 任务集**：memory_on/off 首次出现真实差异
- **Reflection-sensitive v2 任务集**：混合最优策略，验证 reflection 内容增量
- **三组因果对比 benchmark**：baseline / fixed retry / prompt-sensitive retry

## 测试基线

| 指标 | 数值 |
|------|------|
| 测试总数 | 1138 passed, 6 skipped |
| 工具数 | 6（bash/read/write/edit/grep/glob） |
| CLI 命令 | /help, /clear, /reset, /compact, /history, /rollback, /session, /sessions, /inspect |
| 权限模式 | allow-once, allow-session, DENY |
| Memory 任务 | 32（27 baseline + 5 reflection_sensitive_v2） |
| Benchmark runner | run_phase32_memory_eval.py（支持 --with-reflection, --three-group） |

## 关键评测结论

### Memory Benchmark（Phase 3.2E）

基于真实 AgentLoop 执行路径（ScriptedModelClient 驱动，非 mock）：

| 指标 | memory_on | memory_off | 说明 |
|------|-----------|------------|------|
| correct_rate | 70% | 63% | +7pp |
| avg_tool_calls | 0.1 | 1.0 | 10x |
| target_reread_rate | 0% | 100% | memory 避免了 reread |

### Reflection Benchmark（Phase 3.2C + 3.2F）

三组因果对比（reflection_sensitive_v2 子集，5 个任务）：

| 组 | correct | reread | tools | branch_ok |
|----|---------|--------|-------|-----------|
| Baseline（无 retry） | 40% | 40% | 0.4 | — |
| Fixed Retry（统一 reread） | 100% | 100% | 1.4 | 60% |
| Prompt-Sensitive | 100% | 60% | 1.0 | 100% |

**最强结论：** prompt-sensitive retry 相比固定策略减少 40% reread、0.4/任务 tool calls，optimal_branch_match_rate 从 60% 提升到 100%。scripted benchmark 下首次观察到 reflection 内容的额外增量价值。

### 边界说明

- 当前结论基于 scripted benchmark（ScriptedModelClient），不是真实模型上的普遍结论
- reflection 机制尚未接入默认 AgentLoop（仅在 benchmark 层验证）
- 如需更强证明，需做 selective real-model eval

## 当前最适合演示的点

1. **上下文膨胀控制**：长 grep/bash 输出不会撑爆上下文，模型看到 bounded preview
2. **文件修改可回退**：write/edit 前自动备份，/rollback latest 可恢复
3. **权限确认不再笨重**：相同命令/文件可 session 复用批准
4. **真实远程链路可验证**：不只是 fake-model e2e，真实 API 也没断

## 当前成熟度为什么是"接近 Prototype 边缘"

因为虽然主链路、权限、编辑、安全边界和 e2e 已经比较扎实，但仍然缺少：

- session 持久化（当前只在内存中）
- workspace 快照与恢复
- run/resume/inspect 成为一等能力
- 更完整的 integration / smoke 覆盖

## 当前是否可以写进简历

可以，但必须按真实能力写：

### 可以写的
- agent loop、tool system、permission confirmation、diff preview、workspace guard、e2e regression
- Observation Budget 契约、preview + artifact 双层机制
- Backup / Rollback / Edit History
- Session 级 Permission Policy
- 真实远程 LLM Smoke 回归

### 不能写的
- MCP、WebUI、多 agent 并行
- 完整 rollback（只支持 latest）
- 真实完整 e2e benchmark
- production-ready sandbox
- memory / session 产品化
