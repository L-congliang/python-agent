---
title: "feat: 实现上下文压缩模块"
type: feat
date: "2026-06-22"
origin: "docs/brainstorms/2026-06-22-context-compressor-requirements.md"
---

## Summary

实现 `context/compressor.py` 模块，当 token 接近上下文窗口上限时自动压缩旧消息历史。采用滑动窗口 + LLM 摘要的混合方式，保留最近 30% 的原始消息，将更早的消息压缩成摘要。

## Problem Frame

`AgentLoop._messages` 只增不减，长时间对话会超出模型上下文窗口限制，导致 API 报错或 Agent 答非所问。F04 spec 将 Auto Compact、Token Budget 明确留给 F10 实现。

## Requirements

**Token 追踪**

- R1. 扩展 `StreamResult` 添加 `usage` 字段，从 API 响应提取 `input_tokens` 和 `output_tokens`
- R2. `AgentLoop` 维护 `_total_tokens` 计数器，每次 API 调用后累加
- R3. 提供 `token_count` 属性和 `max_tokens` 配置（默认 128K）

**触发机制**

- R4. 当 `_total_tokens >= max_tokens * 0.8` 时自动触发压缩
- R5. 提供 `compact()` 方法供手动触发
- R6. 自动压缩时通过 `_notify()` 显示提示，不暂停对话

**压缩策略**

- R7. 计算保留阈值：`keep_tokens = max_tokens * 0.3`
- R8. 从最新消息向前遍历，累加估算 token 数，直到达到保留阈值
- R9. 将更早的消息发送给 LLM 生成摘要
- R10. 用摘要消息替换原始旧消息，重置 token 计数器

**CLI 集成**

- R11. 在 `app.py` 的 `_handle_command()` 中添加 `/compact` 命令

## Key Technical Decisions

**扩展 StreamResult 而非估算 token**
从 API 响应直接获取 `usage` 字段比本地估算更准确。虽然需要修改 `MimoClient` 和 `StreamResult`，但这是唯一可靠的方式。

**消息 token 估算用于分段**
压缩时需要知道每条消息的 token 数来决定保留哪些消息。使用简单的 `len(content) // 4` 估算，精确度足够用于分段决策。

**压缩 prompt 设计**
使用结构化 prompt 引导 LLM 生成高质量摘要：
```
请将以下对话历史压缩成摘要，保留：
1. 关键决策和结论
2. 用户偏好和约束
3. 重要的上下文信息

丢弃：
1. 详细的工具输出
2. 完整的代码内容
3. 推理过程

对话历史：
{messages}

输出格式：
[摘要] 一段连贯的文字，保留关键信息
```

## High-Level Technical Design

```
┌─────────────────────────────────────────────────────────────┐
│                        AgentLoop                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                    _messages                           │  │
│  │  [msg1, msg2, msg3, ..., msgN]                        │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                   │
│                          ▼                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              _check_compaction()                       │  │
│  │  if _total_tokens >= max_tokens * 0.8:                │  │
│  │      await _compact()                                 │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                   │
│                          ▼                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              ContextCompressor                         │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  1. 分割消息: recent vs old                      │  │  │
│  │  │  2. 生成摘要: LLM compress(old_messages)        │  │  │
│  │  │  3. 重组消息: [summary] + recent                 │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Units

### U1. 扩展 StreamResult 支持 usage

**Goal:** 从 API 响应中提取 token 使用量

**Requirements:** R1

**Files:** `src/agent/core/model.py`, `tests/test_model.py`

**Approach:**
- 在 `StreamResult` dataclass 添加 `usage: dict | None` 字段
- 在 `MimoClient.chat_stream()` 中，从 `stream.get_final_message()` 提取 `.usage` 属性
- 返回包含 `input_tokens` 和 `output_tokens` 的 dict

**Patterns to follow:** 现有 `StreamResult` 的 dataclass 模式

**Test scenarios:**
- Happy path: mock API 返回 usage，StreamResult.usage 正确提取
- Edge case: API 不返回 usage 时，usage 为 None
- Error case: usage 字段格式异常时，graceful fallback 到 None

**Verification:** `uv run pytest tests/test_model.py -x -v` 通过

---

### U2. AgentLoop token 追踪和压缩检查

**Goal:** 维护 token 计数器，检查是否需要压缩

**Requirements:** R2, R3, R4, R5, R6

**Files:** `src/agent/core/loop.py`, `tests/test_agent_loop.py`

**Approach:**
- `__init__` 添加 `_total_tokens: int = 0` 和 `_max_tokens: int = 128_000`
- 每次 API 调用后，从 `StreamResult.usage` 累加 `input_tokens`
- 添加 `token_count` property 和 `compact()` 方法
- 添加 `_check_compaction()` 私有方法，在循环中调用
- `_compact()` 方法调用 `ContextCompressor` 执行压缩
- `_notify()` 方法显示压缩提示（通过 callback 或 print）

**Patterns to follow:** 现有 `_messages` 管理模式

**Test scenarios:**
- Happy path: 多轮对话后 token 计数正确累加
- Happy path: 手动调用 `compact()` 触发压缩
- Edge case: `_total_tokens` 达到阈值时自动触发压缩
- Edge case: 压缩后 `_total_tokens` 重置

**Verification:** `uv run pytest tests/test_agent_loop.py -x -v` 通过

---

### U3. ContextCompressor 压缩逻辑

**Goal:** 实现消息分割、摘要生成、消息重组

**Requirements:** R7, R8, R9, R10

**Files:** `src/agent/context/compressor.py`, `tests/test_compressor.py`

**Approach:**
- `ContextCompressor` 类，接收 `MimoClient` 用于调用 LLM 生成摘要
- `compress(messages: list[dict], keep_tokens: int) -> list[dict]` 方法
  1. 从后向前遍历消息，累加估算 token，找到分割点
  2. 将分割点前的消息格式化为文本
  3. 调用 LLM 生成摘要
  4. 返回 `[summary_message] + recent_messages`
- `_estimate_tokens(text: str) -> int` 简单估算：`len(text) // 4`
- `_format_messages(messages: list[dict]) -> str` 格式化消息为可读文本
- `_generate_summary(formatted: str) -> str` 调用 LLM 生成摘要

**Patterns to follow:** 现有工具的错误处理模式

**Test scenarios:**
- Happy path: 10 条消息，保留最近 3 条，其余压缩成摘要
- Edge case: 所有消息都很短，不需要压缩
- Edge case: 单条消息很长（工具输出），估算 token 准确
- Error case: LLM 调用失败时，返回原始消息（不压缩）
- Integration: 压缩后的消息格式正确，包含 `[摘要]` 标记

**Verification:** `uv run pytest tests/test_compressor.py -x -v` 通过

---

### U4. CLI /compact 命令集成

**Goal:** 用户可通过命令手动触发压缩

**Requirements:** R11

**Files:** `src/agent/cli/app.py`

**Approach:**
- 在 `_handle_command()` 中添加 `if cmd == "/compact":` 分支
- 调用 `self._loop.compact()`
- 显示压缩结果（消息数量变化）

**Patterns to follow:** 现有 `/clear`、`/reset` 命令

**Test scenarios:**
- Happy path: 输入 `/compact` 触发压缩
- Edge case: 消息列表为空时，显示提示

**Verification:** 手动测试或 `uv run pytest tests/test_cli.py -x -v`

## Scope Boundaries

- Session 持久化（F14 负责）
- Token budget 控制（`+500k` 风格的预算功能）
- 压缩历史的回溯/撤销
- 多级压缩策略（如按重要性分级）

## Risks & Dependencies

**依赖**
- mimo API 兼容 Anthropic SDK 的 `usage` 字段返回（需验证）

**风险**
- 如果 API 不返回 usage，需要降级到本地估算（准确度降低）
- LLM 摘要质量取决于模型能力，可能需要优化 prompt

## Sources & Research

- `specs/F04-agent-loop.md` — Auto Compact、Token Budget 的原始设计
- `docs/claude-code-architecture.md:345` — `services/compact/ -> context/compressor.py` 映射
- Claude Code 实践 — 滑动窗口 + 摘要的压缩方式

---

## 后续工作流

**当前状态：** 计划完成，准备执行

**执行顺序：**
1. 🔄 **`/ce-work`** — 按计划实现代码（当前步骤）
2. ⏳ **`/ce-code-review`** — 代码审查（执行完后继续）

**执行完 `/ce-work` 后：**
- 运行 `uv run make check` 确保测试通过
- 输入 `/ce-code-review` 进行代码审查

**`/ce-code-review` 完成后：**
- 运行 `/ce-compound` 记录解决方案
- 更新 `feature_list.json` 中 F10 状态为 `done`
- 更新 `claude-progress.md` 和 `DEV_SYNC.md`
- `git add` → `git commit` → `git push`
