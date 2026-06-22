---
title: "上下文压缩器实现：滑动窗口 + LLM 摘要"
date: "2026-06-22"
category: "architecture-patterns"
module: "context"
problem_type: "architecture_pattern"
component: "assistant"
severity: "medium"
applies_when:
  - "Agent 长时间对话导致 token 超出上下文窗口限制"
  - "需要自动压缩旧消息历史以维持对话能力"
tags:
  - "context-compression"
  - "token-management"
  - "sliding-window"
  - "llm-summary"
---

# 上下文压缩器实现：滑动窗口 + LLM 摘要

## Context

AgentLoop 的 `_messages` 列表只增不减，长时间对话会超出模型上下文窗口限制（mimo v2.5pro 默认 128K tokens），导致 API 报错或 Agent 答非所问。F04 spec 将 Auto Compact、Token Budget 明确留给 F10 实现。

## Guidance

采用**滑动窗口 + LLM 摘要**的混合压缩方式：

1. **Token 追踪**：从 API 响应的 `usage` 字段直接获取 `input_tokens`，比本地估算更准确
2. **自动触发**：当 `_total_tokens >= context_window * 0.8` 时自动压缩
3. **保留策略**：保留最近 30% 的原始消息（`context_window * 0.3`）
4. **摘要生成**：将更早的消息发送给 LLM 生成结构化摘要

### 核心代码结构

```python
# src/agent/context/compressor.py
class ContextCompressor:
    def compress(self, messages: list[dict], keep_tokens: int) -> list[dict]:
        # 1. 从后向前遍历，找到分割点
        split_index = self._find_split_point(messages, keep_tokens)
        # 2. 分割消息
        old_messages = messages[:split_index]
        recent_messages = messages[split_index:]
        # 3. 生成摘要
        summary = self._generate_summary(self._format_messages(old_messages))
        # 4. 重组消息
        return [{"role": "assistant", "content": f"[摘要] {summary}"}] + recent_messages
```

### Token 估算

使用简单的 `len(text) // 4` 估算（1 token ≈ 4 字符），精度足够用于分段决策。精确计算需要 tiktoken 库，增加依赖不值得。

### 降级策略

LLM 摘要失败时，返回原始文本的前 500 字符作为降级摘要，确保压缩不会因 API 错误而完全失败。

## Why This Matters

- **简单截断会丢失重要上下文**：用户偏好、关键决策、约束条件都会丢失
- **LLM 摘要保留关键信息**：通过结构化 prompt 引导 LLM 保留决策、偏好、约束
- **滑动窗口保证近期上下文完整**：最近的对话不受影响，保证 Agent 短期记忆完整

## When to Apply

- Agent 长时间运行（多轮对话超过 50 轮）
- Token 使用量接近上下文窗口限制（>80%）
- 用户手动触发 `/compact` 命令

## Examples

### 压缩前

```
[user]: 帮我写一个 hello world
[assistant]: 好的，这是代码...
[user]: 改成 Python
[assistant]: 这是 Python 版本...
... (50+ 条消息)
[user]: 继续优化
```

### 压缩后

```
[assistant]: [摘要] 用户要求编写 hello world 程序，最初用 JavaScript，后改为 Python。讨论了代码风格和优化方案。
[user]: 继续优化
```

### 配置示例

```python
config = LoopConfig(
    context_window=128_000,  # 上下文窗口大小
    on_notify=lambda msg: print(msg),  # 通知回调
)
loop = AgentLoop(client, registry, config)
```

## Related

- `specs/F04-agent-loop.md` — Auto Compact、Token Budget 的原始设计
- `docs/claude-code-architecture.md` — Claude Code 的 compact 服务映射
