"""Token 计数器 - 精确计算文本的 token 数量

替代现有的 len(text)//4 粗略估算。

设计决策:
- 为什么用 tiktoken？
  OpenAI 的开源 token 计数库，支持 GPT 系列模型。
  mimo 使用 Anthropic 兼容协议，token 计数方式类似。

- 为什么缓存 encoding？
  获取 encoding 对象有一定开销，缓存后整个进程只获取一次。

- 为什么提供 estimate_tokens 作为 fallback？
  tiktoken 可能无法处理某些特殊字符，此时回退到粗略估算。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("agent.context.token_counter")

# 缓存 encoding 对象
_encoding_cache: Any = None


def _get_encoding() -> Any:
    """获取 tiktoken encoding 对象（带缓存）"""
    global _encoding_cache
    if _encoding_cache is not None:
        return _encoding_cache

    try:
        import tiktoken
        # 使用 cl100k_base（GPT-4 和 Claude 使用的编码方式）
        _encoding_cache = tiktoken.get_encoding("cl100k_base")
        logger.info("Using tiktoken cl100k_base encoding")
    except ImportError:
        logger.warning("tiktoken not installed, falling back to estimation")
        _encoding_cache = "fallback"
    except Exception as e:
        logger.warning("Failed to load tiktoken: %s, falling back to estimation", e)
        _encoding_cache = "fallback"

    return _encoding_cache


def count_tokens(text: str) -> int:
    """精确计算文本的 token 数量

    Args:
        text: 要计算的文本

    Returns:
        token 数量
    """
    if not text:
        return 0

    encoding = _get_encoding()

    if encoding == "fallback":
        return estimate_tokens(text)

    try:
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning("tiktoken encode failed: %s, falling back to estimation", e)
        return estimate_tokens(text)


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数量（fallback）

    经验值：1 token ≈ 4 字符（英文）
    对于中文，1 token ≈ 2 字符

    Args:
        text: 要估算的文本

    Returns:
        估算的 token 数量
    """
    if not text:
        return 0

    # 简单估算：字符数 / 4
    return max(1, len(text) // 4)


class TokenCounter:
    """Token 计数器类

    封装 token 计数功能，支持：
    - 单文本计数
    - 批量计数
    - 消息列表计数

    使用方式:
        counter = TokenCounter()
        tokens = counter.count("Hello, world!")
        tokens = counter.count_messages(messages)
    """

    def count(self, text: str) -> int:
        """计算单个文本的 token 数量"""
        return count_tokens(text)

    def count_list(self, texts: list[str]) -> int:
        """计算多个文本的总 token 数量"""
        return sum(count_tokens(text) for text in texts)

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        """计算消息列表的 token 数量

        Anthropic 格式的消息列表：
        [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        每条消息有额外开销（role、格式标记等），估算为 4 token。
        """
        if not messages:
            return 0

        total = 0
        for message in messages:
            # 消息开销（role、格式标记）
            total += 4

            content = message.get("content", "")
            if isinstance(content, str):
                total += count_tokens(content)
            elif isinstance(content, list):
                # Anthropic 的 content blocks 格式
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        if text:
                            total += count_tokens(text)
                    elif isinstance(block, str):
                        total += count_tokens(block)

        return total
