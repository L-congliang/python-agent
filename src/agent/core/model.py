"""
模型层 - mimo API 客户端

封装 mimo v2.5pro API，提供可靠的对话能力。
包含重试、超时、错误处理、日志。

设计决策:
- 用 Anthropic SDK 而不是 httpx：mimo 兼容 Anthropic 协议，SDK 已处理流式解析和错误格式
- 封装 SDK 而不是直接暴露：调用方只关心 messages 和返回的 str，不关心 SDK 细节
"""

from dataclasses import dataclass, field
from collections.abc import Iterator
from typing import Any
import os
import time
import logging

import anthropic
from dotenv import load_dotenv

# 日志记录器
logger = logging.getLogger("agent.model")


@dataclass
class StreamResult:
    """流式调用结果

    同时提供文本 chunk 迭代器和完整的 content blocks。
    解决 text_stream 只包含文本、不包含 tool_use block 的问题。

    使用方式:
        result = client.chat_stream(messages, system)
        for chunk in result.text:       # 流式显示
            print(chunk, end="")
        blocks = result.content_blocks  # 解析 tool_use
        tokens = result.usage           # token 使用量
    """
    text: Iterator[str]
    content_blocks: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] | None = None


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

    def chat(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """同步对话，返回完整回复文本

        Args:
            messages: 对话历史，格式 [{"role": "user", "content": "..."}]
            system: 系统提示词
            tools: 工具定义列表（Anthropic 格式）

        Returns:
            模型回复的文本内容

        Raises:
            anthropic.AuthenticationError: API key 无效
            anthropic.RateLimitError: 请求过于频繁（自动重试后仍失败）
            anthropic.APITimeoutError: 请求超时（自动重试后仍失败）
            anthropic.APIError: 其他 API 错误
        """
        logger.info("API call: %d messages, system=%d chars, tools=%d",
                     len(messages), len(system), len(tools) if tools else 0)
        start_time = time.monotonic()

        def _call() -> str:
            """实际的 API 调用"""
            kwargs: dict[str, Any] = {
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "messages": messages,
                "system": system if system else anthropic.NOT_GIVEN,
            }
            if tools:
                kwargs["tools"] = tools
            response = self._client.messages.create(**kwargs)
            # 提取文本内容
            return response.content[0].text

        result = self._retry(_call)
        elapsed = time.monotonic() - start_time
        logger.info("API response: %d chars, %.2fs", len(result), elapsed)
        return result

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> StreamResult:
        """流式对话，返回文本迭代器 + 完整 content blocks

        返回 StreamResult 而不是 Iterator[str]，因为 tool_use block
        不在 text_stream 中，需要通过 content_blocks 获取。

        Args:
            messages: 对话历史
            system: 系统提示词
            tools: 工具定义列表（Anthropic 格式）

        Returns:
            StreamResult: 包含 text（迭代器）和 content_blocks（流结束后可用）

        Raises:
            同 chat()
        """
        logger.info("API stream call: %d messages, system=%d chars, tools=%d",
                     len(messages), len(system), len(tools) if tools else 0)
        start_time = time.monotonic()
        result = StreamResult(text=iter(()))  # 占位，下面替换

        def _stream() -> Iterator[str]:
            """流式生成器：yield text chunk，return 时填充 content_blocks 和 usage"""
            kwargs: dict[str, Any] = {
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "messages": messages,
                "system": system if system else anthropic.NOT_GIVEN,
            }
            if tools:
                kwargs["tools"] = tools
            with self._client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    yield text
                # 流结束后，获取完整 message 的 content blocks 和 usage
                # 此时 stream 仍处于 open 状态（在 with 块内）
                final_message = stream.get_final_message()
                result.content_blocks = [block.model_dump() for block in final_message.content]
                # 提取 token 使用量
                if final_message.usage:
                    result.usage = {
                        "input_tokens": final_message.usage.input_tokens,
                        "output_tokens": final_message.usage.output_tokens,
                    }

        try:
            result.text = _stream()
            elapsed = time.monotonic() - start_time
            logger.info("API stream setup: %.2fs", elapsed)
        except Exception:
            elapsed = time.monotonic() - start_time
            logger.error("API stream failed: %.2fs", elapsed)
            raise

        return result

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

    自动加载 .env 文件（如果存在）。

    环境变量:
        MIMO_API_KEY: API key（必须）
        MIMO_BASE_URL: API 地址（可选，默认 mimo 官方地址）
        MIMO_MODEL: 模型名称（可选，默认 mimo-v2.5-pro）

    Returns:
        ModelConfig 实例

    Raises:
        ValueError: MIMO_API_KEY 环境变量未设置
    """
    load_dotenv()  # 自动加载 .env 文件
    api_key = os.environ.get("MIMO_API_KEY")
    if not api_key:
        raise ValueError("MIMO_API_KEY 环境变量未设置")

    return ModelConfig(
        api_key=api_key,
        base_url=os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/anthropic"),
        model=os.environ.get("MIMO_MODEL", "mimo-v2.5-pro"),
    )


def create_adapter(model_name: str | None = None) -> Any:
    """根据模型名称创建对应的适配器。

    Args:
        model_name: 模型名称。如果为 None，从环境变量读取。

    Returns:
        ModelAdapter 实例（MimoAdapter 或 DeepSeekAdapter）。

    Raises:
        ValueError: 不支持的模型名称。
    """
    # 延迟导入，避免循环依赖
    from .adapters.mimo_adapter import MimoAdapter
    from .adapters.deepseek_adapter import DeepSeekAdapter

    # 模型名 → 适配器类的映射
    adapter_map = {
        "mimo-v2.5-pro": MimoAdapter,
        "mimo": MimoAdapter,
        "deepseek-v4-pro": DeepSeekAdapter,
        "deepseek": DeepSeekAdapter,
    }

    model = model_name or os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")
    adapter_cls = adapter_map.get(model)

    if adapter_cls is None:
        # 默认使用 mimo 适配器
        logger.warning("Unknown model '%s', defaulting to MimoAdapter", model)
        adapter_cls = MimoAdapter

    return adapter_cls()
