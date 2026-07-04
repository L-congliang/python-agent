---
title: "feat: Memory V1 — ContextManager 接入运行时 + 分层注入"
type: feat
date: 2026-07-04
origin: docs/brainstorms/2026-07-04-memory-v1-context-manager-requirements.md
---

## Summary

将 ContextManager 从死代码升级为 prompt 构建主入口，SystemPromptBuilder 仅负责静态前缀；记忆区改为分层注入（task → recent_files → file_summaries top-k → episodic_notes 检索命中），新增 history formatter 将 messages 转为结构化摘要。

## Problem Frame

当前 `_build_system_prompt()` 直接调用 `SystemPromptBuilder.build()`，该方法把 identity、behavior、tool_guide、memory.render()、tool list 一次性拼接，无 token 预算控制。ContextManager 在 loop.py line 162 被实例化但从未调用，其 12,000 token 预算裁剪机制是死代码。记忆注入走全量 `memory.render()`，episodic notes 只报数量不报内容，file_summaries 无相关性筛选。

## Requirements

### ContextManager 接入

R1. `_build_system_prompt()` 调用 `ContextManager.build_prompt()` 而非 `SystemPromptBuilder.build()`。

R2. SystemPromptBuilder 新增 `build_prefix()` 方法，只返回 identity + behavior + tool_guide 静态内容，不拼装 dynamic context。

R3. history formatter 将 `self._messages` 转为结构化摘要字符串：成功的 tool 调用保留 tool 名 + path/command + 摘要预览（120-300 chars）；失败的 tool_result 保留完整错误信息；超长预览加 `...(truncated)`。

### 记忆分层注入

R4. 记忆不再走全量 `memory.render()`。组装顺序固定为 task → recent_files → relevant file_summaries → retrieved episodic_notes。

R5. MemoryManager 新增 `select_relevant_file_summaries(query, top_k=3)` 方法。V1 用简单规则：recent_files 优先、路径名与 query 关键词重叠、最近访问优先。

R6. `search_notes(user_input)` 接入注入链路，检索 top-k episodic notes 并注入内容。

R7. search_notes 无命中时不注入 note 内容，只保留 notes count 或留空。

### 验证

R8. memory_experiment 14 任务真实模型：correct_rate 不退化（基线 memory_on=100%）。

R9. repeated_reads 至少不恶化（基线 memory_on=1）。

## Key Technical Decisions

**KTD1: ContextManager 保持 5-section 签名不变。** memory 层在调用前由 MemoryManager 组装成一个字符串传入。理由：改动面最小，ContextManager 保持通用性，memory 分层逻辑内聚在 MemoryManager 内部。budget 的 memory section (1600 tokens) 作为组装时的硬约束。

**KTD2: SystemPromptBuilder 降级为静态前缀提供者。** `build_prefix()` 返回 identity + behavior + tool_guide（~380 tokens）。`build_dynamic_context()` 不再被调用。理由：避免与 ContextManager 重复拼装 tools/memory。

**KTD3: history formatter 独立成新模块。** 不塞进 loop.py 或 ContextManager。理由：职责单一，可独立测试，不污染现有模块。

**KTD4: memory 组装顺序固定为 task → recent_files → file_summaries → episodic_notes。** 理由：实验可解释性。如果 memory section 被截断，先丢 episodic_notes（最低优先级），再丢 file_summaries，task 和 recent_files 优先保留。

## High-Level Technical Design

```
当前流程:
  _build_system_prompt()
    → SystemPromptBuilder.build()
      → memory.render() [全量塞入]
    → 返回 prompt string

V1 流程:
  _build_system_prompt()
    → prefix = SystemPromptBuilder.build_prefix()  [静态 ~380 tokens]
    → tools = registry.format_tools()
    → memory = MemoryManager.assemble_layered(query, budget=1600)
        → task (总是注入)
        → recent_files (总是注入 top 3-5)
        → file_summaries = select_relevant_file_summaries(query, top_k=3)
        → episodic_notes = search_notes(query) → 注入 top 1-3
    → history = format_history(messages)  [结构化摘要]
    → prompt, metadata = ContextManager.build_prompt(prefix, tools, memory, history, current_request)
    → 返回 prompt, 保存 metadata
```

## Implementation Units

### U1. SystemPromptBuilder.build_prefix()

**Goal:** 提取静态前缀，使 SystemPromptBuilder 不再负责 dynamic context 拼装。

**Requirements:** R2

**Dependencies:** 无

**Files:**
- `src/agent/prompts/builder.py` — 新增 `build_prefix()` 静态方法
- `tests/test_builder.py` — 新增测试

**Approach:**
- 新增 `build_prefix()` 类方法，返回 `build_identity() + "\n\n" + build_behavior_guidelines() + "\n\n" + build_tool_selection_guide()`
- `build()` 方法保留向后兼容，但内部改用 `build_prefix()` + `build_dynamic_context()`
- `build_dynamic_context()` 保留但标记为 deprecated，不再被主循环调用

**Test scenarios:**
- `build_prefix()` 返回包含 identity、behavior、tool_guide 三部分内容
- `build_prefix()` 不包含 memory、tools 列表、subagent 指南
- `build_prefix()` 输出长度稳定在 ~380 tokens

**Verification:** `build_prefix()` 可独立调用，返回纯静态内容。

---

### U2. History Formatter

**Goal:** 将 `_messages: list[dict]` 转为结构化摘要字符串，不保留完整 tool_output。

**Requirements:** R3

**Dependencies:** 无

**Files:**
- `src/agent/context/history_formatter.py` — 新建模块
- `tests/test_history_formatter.py` — 新建测试

**Approach:**
- 新建 `format_history(messages: list[dict], max_tokens: int = 4000) -> str`
- user/assistant 文本消息正常保留
- tool_result 转为摘要行：
  - 成功的 read: `tool=read path=xxx lines=N chars=M | preview: ...`
  - 成功的 grep/glob/bash: `tool=xxx query/cmd=xxx hits=N | preview: ...`
  - 成功的 write/edit: `tool=xxx path=xxx | result: ...`
  - 失败的 tool_result: 保留完整错误信息
- 超长预览统一加 `...(truncated)`
- 从消息末尾向前截断，保留最近消息优先

**Test scenarios:**
- 纯文本消息正常保留
- 成功的 read tool_result 转为摘要行（包含 path、行数、预览）
- 失败的 tool_result 保留完整错误信息
- 超长预览被截断并加 `...(truncated)`
- 超出 max_tokens 时从前面截断，保留最近消息
- 空消息列表返回空字符串

**Verification:** 格式化后的 history 字符串不含完整文件内容，token 数在预算内。

---

### U3. MemoryManager 分层组装

**Goal:** 将记忆从全量 render() 改为分层组装，支持相关性筛选和 search_notes 注入。

**Requirements:** R4, R5, R6, R7

**Dependencies:** 无

**Files:**
- `src/agent/memory/manager.py` — 新增 `assemble_layered()` 和 `select_relevant_file_summaries()`
- `src/agent/memory/renderer.py` — 新增分层渲染方法
- `tests/test_memory_manager.py` — 新增测试
- `tests/test_memory_renderer.py` — 新增测试

**Approach:**
- 新增 `MemoryManager.assemble_layered(query: str, max_tokens: int = 1600) -> str`
  - 按顺序组装：task → recent_files → file_summaries → episodic_notes
  - 每层估算 token，超出预算时从后往前截断
- 新增 `MemoryManager.select_relevant_file_summaries(query: str, top_k: int = 3) -> list[dict]`
  - 规则1: recent_files 中的文件优先
  - 规则2: 路径名与 query 有关键词重叠
  - 规则3: 最近访问优先（mtime）
  - 只返回 fresh 的 summaries
- 新增 `MemoryRenderer.render_task() -> str`
- 新增 `MemoryRenderer.render_recent_files() -> str`
- 新增 `MemoryRenderer.render_file_summaries(files: list[dict]) -> str`
- 新增 `MemoryRenderer.render_episodic_notes(notes: list[dict]) -> str`
- `search_notes(query)` 已存在，直接调用

**Test scenarios:**
- `assemble_layered()` 返回包含 task、recent_files、file_summaries、episodic_notes 各层
- `select_relevant_file_summaries()` recent_files 中的文件排在前面
- `select_relevant_file_summaries()` 路径名匹配 query 的文件被选中
- `select_relevant_file_summaries()` 只返回 fresh 的 summaries
- `assemble_layered()` 超出 max_tokens 时从后往前截断
- search_notes 无命中时不注入 note 内容
- `render_episodic_notes()` 格式化包含 text 和 tags

**Verification:** 分层组装后的 memory 字符串包含各层内容，token 数在预算内。

---

### U4. Wire ContextManager into _build_system_prompt()

**Goal:** 将 ContextManager 接入主循环 prompt 构建，替代 SystemPromptBuilder.build()。

**Requirements:** R1

**Dependencies:** U1, U2, U3

**Files:**
- `src/agent/core/loop.py` — 重写 `_build_system_prompt()`
- `tests/test_loop.py` — 更新/新增测试

**Approach:**
- `_build_system_prompt()` 改为：
  1. `prefix = SystemPromptBuilder.build_prefix()`
  2. `tools = self._registry.format_tools()`
  3. `query = self._memory.get_task_summary() or self._last_user_input`
  4. `memory = self._memory.assemble_layered(query, max_tokens=self._context_manager.get_section_budget("memory"))`
  5. `history = format_history(self._messages)`
  6. `prompt, metadata = self._context_manager.build_prompt(prefix, tools, memory, history, current_request)`
  7. `self._last_context_metadata = metadata`
  8. 返回 prompt
- 保留 `memory_enabled` 开关：`memory_enabled=False` 时传空字符串给 memory section
- `_build_subagent_prompt()` 保持使用 `render_compact()` 不变

**Test scenarios:**
- `_build_system_prompt()` 返回的 prompt 包含 prefix、tools、memory、history、current_request 各部分
- `memory_enabled=False` 时 memory section 为空
- `_last_context_metadata` 被正确设置
- prompt 总 token 不超过 12,000 预算
- 子 Agent prompt 不受影响（仍用 render_compact）

**Verification:** `_build_system_prompt()` 走 ContextManager 路径，返回的 prompt 结构正确。

---

### U5. 记忆实验验证

**Goal:** 跑 14 任务真实模型实验，验证 V1 不退化。

**Requirements:** R8, R9

**Dependencies:** U1, U2, U3, U4

**Files:**
- `docs/test-reports/P2-memory-experiment.md` — 更新实验报告

**Approach:**
- 运行 `memory_experiment.py --real` 三轮
- 对比 V1 前后的 correct_rate、repeated_reads、memory_hit_rate
- 基线：memory_on=100%, memory_off=86%, memory_irrelevant=93%
- V1 目标：memory_on correct_rate ≥ 100%, repeated_reads ≤ 1

**Test scenarios:**
- memory_on correct_rate 不低于 100%
- memory_on repeated_reads 不高于 1
- memory_hit_rate 不退化
- ContextMetadata 显示各 section 的 rendered_tokens 和 was_truncated 状态

**Verification:** 三轮实验结果稳定，无退化。

## Scope Boundaries

**Deferred for later (V2):**
- file_summaries 语义摘要升级（从截断升级为结构化摘要）
- freshness/invalidation 机制强化
- notes 噪声治理策略（按 tag 限流、error 聚合）
- durable promotion 策略
- ContextManager budget 调参（基于 V1 实验数据）

**Outside this scope (V3):**
- 多 Agent 记忆隔离策略
- 父子 Agent 回灌协议
- durable memory 按主题分层

## Risks & Dependencies

**Risk: prompt 结构变化导致模型行为变化。** V1 改变了 prompt 的组装方式（从 SystemPromptBuilder 直接拼接到 ContextManager 预算裁剪），可能导致模型在某些任务上的行为不同。Mitigation: 跑 14 任务实验验证不退化。

**Risk: history formatter 丢失关键上下文。** 摘要化 tool_result 可能丢弃模型需要的细节。Mitigation: 失败的 tool_result 保留完整错误信息；如果实验发现退化，可调整摘要策略。

**Risk: memory 1600 token 预算不够。** task + recent_files + file_summaries + episodic_notes 可能超过 1600 tokens。Mitigation: V1 先跑实验看截断率，如果频繁截断再做 V1.1 budget rebalance。

## Sources / Research

- 需求文档: `docs/brainstorms/2026-07-04-memory-v1-context-manager-requirements.md`
- 记忆实验基线: `docs/test-reports/P2-memory-experiment.md`（14 任务，memory_on 100% vs memory_off 86%）
- ContextManager 已有 23 个测试: `tests/test_context_manager.py`
- Retrieval 已有 4 个测试: `tests/test_retrieval.py`
- P6 prompt ablation: identity 从 13.6% → 59.1% tool_accuracy（静态前缀必须完整保留）
