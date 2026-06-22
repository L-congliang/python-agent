"""
上下文压缩器 - 当 token 接近上限时自动压缩旧消息

采用滑动窗口 + LLM 摘要的混合方式：
- 保留最近 30% 的原始消息
- 将更早的消息压缩成摘要

设计决策:
- 为什么用 len(text) // 4 估算 token？
  这是粗略估算（1 token ≈ 4 字符），精度足够用于分段决策。
  精确计算需要 tiktoken 库，增加依赖不值得。

- 为什么保留最近 30%？
  太少会丢失近期上下文，太多则压缩效果差。
  30% 是经验值，Claude Code 也用类似比例。

- 为什么用 LLM 生成摘要而不是简单截断？
  简单截断会丢失重要上下文（如用户偏好、关键决策）。
  LLM 摘要能保留关键信息，提高后续对话质量。
"""

from __future__ import annotations

import logging
from typing import Any

from agent.core.model import MimoClient

logger = logging.getLogger("agent.compressor")

# 压缩 prompt 模板
SUMMARY_PROMPT = """请将以下对话历史压缩成摘要，保留：
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
[摘要] 一段连贯的文字，保留关键信息"""


class ContextCompressor:
    """上下文压缩器

    职责:
    - 分割消息：recent（保留）vs old（压缩）
    - 调用 LLM 生成摘要
    - 重组消息：[summary] + recent

    使用方式:
        compressor = ContextCompressor(client)
        compressed = compressor.compress(messages, keep_tokens=30000)
    """

    def __init__(self, client: MimoClient) -> None:
        """初始化压缩器

        Args:
            client: mimo API 客户端，用于调用 LLM 生成摘要
        """
        self._client = client

    def compress(self, messages: list[dict[str, Any]], keep_tokens: int) -> list[dict[str, Any]]:
        """压缩消息历史

        Args:
            messages: 完整的消息历史
            keep_tokens: 保留的 token 数量（从最新消息向前累加）

        Returns:
            压缩后的消息列表：[summary_message] + recent_messages
            如果不需要压缩，返回原始消息
        """
        if not messages:
            return messages

        # 1. 从后向前遍历，找到分割点
        split_index = self._find_split_point(messages, keep_tokens)

        # 如果所有消息都在保留范围内，不需要压缩
        if split_index == 0:
            logger.info("No compression needed: all messages within keep_tokens")
            return messages

        # 2. 分割消息
        old_messages = messages[:split_index]
        recent_messages = messages[split_index:]

        logger.info(
            "Compressing %d old messages, keeping %d recent messages",
            len(old_messages),
            len(recent_messages),
        )

        # 3. 生成摘要
        formatted = self._format_messages(old_messages)
        summary = self._generate_summary(formatted)

        # 4. 重组消息
        summary_message = {
            "role": "assistant",
            "content": f"[摘要] {summary}",
        }

        compressed = [summary_message] + recent_messages
        logger.info("Compression complete: %d messages -> %d messages", len(messages), len(compressed))

        return compressed

    def _find_split_point(self, messages: list[dict[str, Any]], keep_tokens: int) -> int:
        """找到分割点：从后向前累加 token，直到达到 keep_tokens

        Args:
            messages: 消息列表
            keep_tokens: 要保留的 token 数量

        Returns:
            分割点索引（该索引及之后的消息保留）
        """
        accumulated = 0
        for i in range(len(messages) - 1, -1, -1):
            content = self._get_message_content(messages[i])
            tokens = self._estimate_tokens(content)
            accumulated += tokens

            if accumulated >= keep_tokens:
                return i

        # 所有消息都在保留范围内
        return 0

    def _estimate_tokens(self, text: str) -> int:
        """估算文本的 token 数量

        简单估算：1 token ≈ 4 字符（中英文混合场景）

        Args:
            text: 文本内容

        Returns:
            估算的 token 数量
        """
        return len(text) // 4

    def _get_message_content(self, message: dict[str, Any]) -> str:
        """提取消息的文本内容

        Args:
            message: 消息字典

        Returns:
            消息的文本内容
        """
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # 处理 tool_result 等复杂内容
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        parts.append(str(block.get("content", "")))
                elif isinstance(block, str):
                    parts.append(block)
            return " ".join(parts)
        return str(content)

    def _format_messages(self, messages: list[dict[str, Any]]) -> str:
        """将消息格式化为可读文本

        Args:
            messages: 消息列表

        Returns:
            格式化后的文本
        """
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = self._get_message_content(msg)
            parts.append(f"[{role}]: {content}")
        return "\n\n".join(parts)

    def _generate_summary(self, formatted: str) -> str:
        """调用 LLM 生成摘要

        Args:
            formatted: 格式化后的消息文本

        Returns:
            摘要文本

        Raises:
            Exception: LLM 调用失败时返回原始文本的截断版本
        """
        prompt = SUMMARY_PROMPT.format(messages=formatted)

        try:
            summary = self._client.chat([{"role": "user", "content": prompt}])
            logger.info("Summary generated: %d chars", len(summary))
            return summary
        except Exception as e:
            logger.error("Failed to generate summary: %s", e)
            # 降级：返回原始文本的前 500 字符
            fallback = formatted[:500] + "..." if len(formatted) > 500 else formatted
            return f"[压缩失败，保留原始内容] {fallback}"
