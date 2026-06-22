---
date: "2026-06-22"
topic: context-compressor
---

## Summary

构建上下文压缩模块（`context/compressor.py`），当 token 接近上限时自动压缩旧消息历史。保留最近消息的原始内容，将更早的消息通过 LLM 生成摘要。核心原则：保留结论，丢弃过程。

## Problem Frame

长时间对话时，消息历史不断累积，最终会超出模型的上下文窗口限制。目前系统没有任何压缩机制，`_messages` 列表只增不减，导致：
- API 调用报错（token 超限）
- Agent 开始"答非所问"（上下文被截断或模型注意力分散）

## Requirements

**触发机制**

- R1. 当 token 数达到上下文窗口的 80% 时，自动触发压缩
- R2. 用户可通过 `/compact` 命令手动触发压缩
- R3. 自动压缩时显示一行提示（如 "Auto-compact: context window 85% full, compressing history..."），但不暂停对话

**压缩策略**

- R4. 采用滑动窗口 + 摘要的混合方式：保留最近 30% token 空间的消息为原始内容，更早的消息压缩成摘要
- R5. 摘要通过 LLM（mimo API）生成，侧重保留决策、结论、关键信息，丢弃详细的工具输出和推理过程
- R6. 工具调用结果（file_read、bash、grep 等输出）压缩进摘要，不单独保留原始内容

**Token 计算**

- R7. 每次 API 调用后，累加响应中的 `input_tokens` 到总 token 计数器
- R8. 压缩完成后重置计数器

**不可逆性**

- R9. 压缩后不保留原始历史，只保留摘要（与 Claude Code 行为一致）

## Key Decisions

**摘要质量优先于压缩速度**
用 LLM 生成摘要而非简单截断，确保不丢失重要上下文。虽然增加延迟和成本，但这是核心目标"不丢失重要上下文"的必要代价。

**通知但不打断**
压缩时显示一行提示，但不询问确认、不暂停对话。平衡用户知情权和对话流畅性。

**按 token 比例而非固定数量**
保留最近 30% token 空间的消息，而非固定保留 N 条。自适应消息长度差异，保证摘要和原始消息的比例稳定。

## Scope Boundaries

- Session 持久化（F14 负责）
- Token budget 控制（`+500k` 风格的预算功能，后续实现）
- 压缩历史的回溯/撤销
- 多级压缩策略（如按重要性分级）

## Outstanding Questions

- Deferred to Planning: mimo API 的上下文窗口大小是多少？（8K / 32K / 128K？需要查证）
- Deferred to Planning: 压缩 prompt 的具体设计（如何引导 LLM 生成高质量摘要）
