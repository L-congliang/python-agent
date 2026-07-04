---
date: 2026-07-04
topic: memory-v1-context-manager
---

## Summary

将 ContextManager 升级为运行时 prompt 组装主入口，SystemPromptBuilder 仅负责静态前缀内容；记忆区改为按层注入，其中 task 与 recent_files 固定注入，file_summaries 依据简单相关性规则选取 top-k，episodic_notes 通过 search_notes(user_input) 检索命中后注入 1-3 条内容。

## Problem Frame

当前记忆系统存在两个结构性问题：

1. **ContextManager 是死代码。** 它在 loop.py 中被实例化（line 162），但 _build_system_prompt() 直接走 SystemPromptBuilder.build()，完全绕过了预算裁剪链路。prompt 长度不受控，记忆、工具、历史消息各自为政。

2. **记忆注入是"全量 render 后塞"。** memory.render() 把 task、recent_files、file_summaries、episodic_notes、durable_topics 全部格式化后一次性塞入 prompt。没有按相关性筛选，没有预算控制，episodic_notes 只报数量不报内容。

## Key Decisions

**SystemPromptBuilder 降级为静态内容提供者。** 它不再负责最终 prompt 拼装，只产出 identity + behavior + tool guide 等静态前缀。ContextManager 接收这些前缀，连同 tools、memory、history、current_request，统一做预算裁剪和组装。这避免了 tools/memory 重复拼装，也让 token 预算能按 section 精细控制。

**search_notes 先用 user_input 做查询。** 不构造复杂 query，直接用当前用户输入检索 episodic notes。够用再升级。

**episodic notes 注入设兜底策略。** 若 search_notes() 无命中，不注入 note 内容，只保留 notes count 或留空。不会因为检索不到就把 prompt 结构打坏。

**file_summaries 用简单规则做 top-k 选择。** V1 不做语义检索，用命中 recent_files、路径名与 user_input 关键词重叠、最近访问优先等规则。新增 MemoryManager.select_relevant_file_summaries(query, top_k) 方法。

## Requirements

### ContextManager 接入

R1. _build_system_prompt() 不再直接返回 SystemPromptBuilder.build(...) 的结果。改为调用 ContextManager.build_prompt()。

R2. SystemPromptBuilder 拆分为静态前缀提供者。新增方法（如 build_prefix()）只产出 identity + behavior + tool guide，不拼装 dynamic context。

R3. ContextManager.build_prompt() 接收 5 个 section：prefix（来自 SystemPromptBuilder）、tools（来自 registry）、memory（来自分层注入）、history（来自 messages 格式化）、current_request（当前用户输入）。

R4. 新增 history 格式化逻辑。谁把 self._messages: list[dict] 转成 history: str。转换规则：保留 user/assistant 交替消息，保留 tool_result 内容摘要，裁掉超出 history 预算的早期消息。

### 记忆分层注入

R5. 记忆不再走全量 memory.render() 直接塞入。改为按层组装：task（总是注入）、recent_files（总是注入最近 3-5 个）、file_summaries（按相关性取 top-k）、episodic_notes（search_notes 命中后注入 1-3 条内容）。

R6. 新增 MemoryManager.select_relevant_file_summaries(query, top_k=3) 方法。V1 用简单规则：命中 recent_files 优先、路径名与 query 关键词重叠、最近访问优先。

R7. search_notes(user_input) 接入注入链路。用当前用户输入检索 top-k episodic notes，将命中内容注入 prompt 的 memory 区。

R8. episodic notes 无命中兜底。若 search_notes() 返回空，不注入 note 内容，只保留 notes count 或留空。

### 验证

R9. memory_experiment 跑完后 correct_rate 不退化（当前 memory_on=100%）。

R10. repeated_reads 至少不恶化（当前 memory_on=1）。

## Scope Boundaries

**Deferred for later (V2):**
- file_summaries 语义摘要升级（从截断升级为结构化摘要）
- freshness/invalidation 机制强化
- notes 噪声治理策略（按 tag 限流、error 聚合）
- durable promotion 策略

**Outside this scope (V3):**
- 多 Agent 记忆隔离策略
- 父子 Agent 回灌协议
- durable memory 按主题分层

## Acceptance Examples

AE1. **ContextManager 接管后 prompt 结构正确。** 构造一个包含记忆、工具、历史的场景，验证 build_prompt() 输出的 prompt 包含 prefix、tools、memory（分层）、history、current_request 各 section，且总 token 不超过预算。

AE2. **search_notes 命中内容进入 prompt。** 先 append_note("API_KEY is sk-xxx"), 再用 "What is the API_KEY?" 作为 user_input，验证 search_notes 命中后该内容出现在 prompt 的 memory 区。

AE3. **search_notes 无命中时兜底。** 用不相关的 query 调用 search_notes，验证返回空时不注入 note 内容，prompt 结构不被破坏。

AE4. **file_summaries top-k 选择。** 有 5 个 file summaries，recent_files 包含其中 2 个，query 匹配另外 1 个路径名。验证 select_relevant_file_summaries(query, top_k=3) 返回这 3 个。

## Success Criteria

- _build_system_prompt() 走 ContextManager.build_prompt() 路径
- memory 区不再走全量 render() 直接塞入
- search_notes() 命中内容真实进入 prompt
- memory_experiment correct_rate 不退化，repeated_reads 至少不恶化
- 面试能讲清楚"为什么 ContextManager 接管 prompt 构建"和"记忆分层注入的设计思路"

## Dependencies / Assumptions

- ContextManager 的 token 计数器（TiktokenCounter）准确
- EpisodicNotes 的 search_notes() 在当前数据量下返回有意义的结果
- 12,000 token 预算足够容纳 prefix + tools + memory + history + current_request

## Outstanding Questions

**Resolved:**
- history 格式化：不保留完整 tool_result，默认只保留结构化摘要；失败结果保留更完整错误信息。具体规则：成功的 read 保留 path + 行数/字符数 + 最多 120-200 chars 预览；成功的 grep/glob/bash 保留查询/命令 + 命中数/退出状态 + 最多 200-300 chars 预览；成功的 write/edit 保留 path + 修改结果摘要；失败的 tool_result 尽量多保留错误信息；超长预览统一加 ...(truncated)。
- Context budget：V1 维持 12,000 不变。先接管运行链路并跑 memory experiment，若 memory 区频繁被截断且 history/tools 长期富余，再做 V1.1 的 budget rebalance。

**Deferred to Planning:**
- select_relevant_file_summaries 的具体匹配规则细节
- 哪些 episodic notes 质量足够高值得注入
