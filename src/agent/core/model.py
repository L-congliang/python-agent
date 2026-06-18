"""
模型层 - mimo API 客户端

封装 mimo v2.5pro API，提供可靠的对话能力。
包含重试、超时、错误处理、日志。

设计决策:
- 用 Anthropic SDK 而不是 httpx：mimo 兼容 Anthropic 协议，SDK 已处理流式解析和错误格式
- 封装 SDK 而不是直接暴露：调用方只关心 messages 和返回的 str，不关心 SDK 细节
"""

from dataclasses import dataclass
from collections.abc import Iterator
from typing import Any
import os
import time
import logging

import anthropic

# 日志记录器
logger = logging.getLogger("agent.model")


@dataclass
class ModelConfig:
    """模型配置

    所有参数都有合理默认值，只需要提供 api_key 即可启动。
    通过环境变量或构造函数参数配置。
    """
    api_key: str
    base_url: str = "https://token-plan-cn.xiaomimimo.com/anthropic"
    model: str = "mimo-v2.5-pro"
    max_tokens: int = 4096
    timeout: float = 60.0          # 单次请求超时（秒）
    max_retries: int = 3           # 最大重试次数
    retry_delay: float = 1.0       # 重试间隔基数（秒）


class MimoClient:
    """mimo API 客户端

    职责:
    - 管理 API 连接
    - 提供同步/流式两种对话方式
    - 统一处理重试、超时、错误
    - 记录调用日志

    使用方式:
        config = ModelConfig(api_key="xxx")
        client = MimoClient(config)

        # 同步对话
        reply = client.chat([{"role": "user", "content": "你好"}])

        # 流式对话
        for chunk in client.chat_stream([{"role": "user", "content": "你好"}]):
            print(chunk, end="", flush=True)
    """

    def __init__(self, config: ModelConfig) -> None:
        """初始化客户端

        Args:
            config: 模型配置
        """
        self.config = config
        self._client = anthropic.Anthropic(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )
        logger.info("MimoClient initialized: model=%s, base_url=%s", config.model, config.base_url)

    def chat(self, messages: list[dict[str, str]], system: str = "") -> str:
        """同步对话，返回完整回复文本

        Args:
            messages: 对话历史，格式 [{"role": "user", "content": "..."}]
            system: 系统提示词

        Returns:
            模型回复的文本内容

        Raises:
            anthropic.AuthenticationError: API key 无效
            anthropic.RateLimitError: 请求过于频繁（自动重试后仍失败）
            anthropic.APITimeoutError: 请求超时（自动重试后仍失败）
            anthropic.APIError: 其他 API 错误
        """
        logger.info("API call: %d messages, system=%d chars", len(messages), len(system))
        start_time = time.monotonic()

        def _call() -> str:
            """实际的 API 调用"""
            response = self._client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                messages=messages,
                system=system if system else anthropic.NOT_GIVEN,
            )
            # 提取文本内容
            return response.content[0].text

        result = self._retry(_call)
        elapsed = time.monotonic() - start_time
        logger.info("API response: %d chars, %.2fs", len(result), elapsed)
        return result

    def chat_stream(self, messages: list[dict[str, str]], system: str = "") -> Iterator[str]:
        """流式对话，逐块返回文本

        Args:
            messages: 对话历史
            system: 系统提示词

        Yields:
            每个文本块（chunk）

        Raises:
            同 chat()
        """
        logger.info("API stream call: %d messages, system=%d chars", len(messages), len(system))
        start_time = time.monotonic()

        def _stream() -> Iterator[str]:
            """实际的流式 API 调用"""
            with self._client.messages.stream(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                messages=messages,
                system=system if system else anthropic.NOT_GIVEN,
            ) as stream:
                for text in stream.text_stream:
                    yield text

        # 流式调用需要特殊处理重试：第一次迭代成功后就不再重试
        # 这里简化处理：直接调用，出错时由调用方处理
        # TODO: 如果需要流式重试，需要缓存已收到的 chunks
        try:
            yield from _stream()
            elapsed = time.monotonic() - start_time
            logger.info("API stream completed: %.2fs", elapsed)
        except Exception:
            elapsed = time.monotonic() - start_time
            logger.error("API stream failed: %.2fs", elapsed)
            raise

    def _retry(self, fn: Any) -> Any:
        """指数退避重试

        对可重试的错误（限流、超时、连接错误）进行重试。
        认证错误和其他 API 错误不重试。

        Args:
            fn: 要重试的函数

        Returns:
            fn 的返回值

        Raises:
            最后一次重试仍然失败时，抛出原始异常
        """
        last_exception = None

        for attempt in range(self.config.max_retries):
            try:
                return fn()
            except anthropic.AuthenticationError:
                # 认证错误不重试，直接抛出
                logger.error("Authentication failed: invalid API key")
                raise
            except anthropic.RateLimitError as e:
                last_exception = e
                if attempt == self.config.max_retries - 1:
                    logger.error("Rate limit exceeded after %d retries", self.config.max_retries)
                    raise
                wait = self.config.retry_delay * (2 ** attempt)
                logger.warning("Rate limited, retrying in %.1fs (attempt %d/%d)", wait, attempt + 1, self.config.max_retries)
                time.sleep(wait)
            except anthropic.APITimeoutError as e:
                last_exception = e
                if attempt == self.config.max_retries - 1:
                    logger.error("Timeout after %d retries", self.config.max_retries)
                    raise
                wait = self.config.retry_delay * (2 ** attempt)
                logger.warning("Timeout, retrying in %.1fs (attempt %d/%d)", wait, attempt + 1, self.config.max_retries)
                time.sleep(wait)
            except anthropic.APIConnectionError as e:
                last_exception = e
                if attempt == self.config.max_retries - 1:
                    logger.error("Connection failed after %d retries", self.config.max_retries)
                    raise
                wait = self.config.retry_delay * (2 ** attempt)
                logger.warning("Connection failed, retrying in %.1fs (attempt %d/%d)", wait, attempt + 1, self.config.max_retries)
                time.sleep(wait)
            except anthropic.APIError as e:
                # 其他 API 错误不重试
                logger.error("API error: %s", str(e))
                raise

        # 不应该走到这里，但为了类型安全
        raise last_exception  # type: ignore[misc]


def load_config() -> ModelConfig:
    """从环境变量加载配置

    环境变量:
        MIMO_API_KEY: API key（必须）
        MIMO_BASE_URL: API 地址（可选，默认 mimo 官方地址）
        MIMO_MODEL: 模型名称（可选，默认 mimo-v2.5-pro）

    Returns:
        ModelConfig 实例

    Raises:
        ValueError: MIMO_API_KEY 环境变量未设置
    """
    api_key = os.environ.get("MIMO_API_KEY")
    if not api_key:
        raise ValueError("MIMO_API_KEY 环境变量未设置")

    return ModelConfig(
        api_key=api_key,
        base_url=os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/anthropic"),
        model=os.environ.get("MIMO_MODEL", "mimo-v2.5-pro"),
    )
