"""模型适配器协议。

不同模型（mimo、DeepSeek 等）的 API 响应有差异：
- 取回答文本的方式不同（mimo 直接取 content[0]，DeepSeek 要跳过 ThinkingBlock）
- 工具调用的文本格式不同（mimo 用 XML，DeepSeek 用 HTML）

适配器只负责**解析响应**，不负责 SDK 调用。
SDK 调用由 MimoClient 处理（包括流式），适配器从 content_blocks 中提取内容。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ToolCall:
    """解析后的工具调用。"""

    name: str
    arguments: dict[str, Any]
    id: str = field(default_factory=lambda: f"toolu_{uuid.uuid4().hex[:24]}")


@dataclass
class ParsedResponse:
    """解析后的统一响应结构。

    Attributes:
        text: 干净的回答文本（已去除 ThinkingBlock 等非回答内容）。
        tool_calls: 解析好的工具调用列表，纯文本回答时为空列表。
    """

    text: str
    tool_calls: list[ToolCall]


@runtime_checkable
class ModelAdapter(Protocol):
    """模型适配器协议。

    每个模型（mimo、DeepSeek 等）实现这个协议，
    封装该模型特有的响应解析差异。

    注意：适配器不负责 SDK 调用，只负责解析。
    SDK 调用（包括流式）由 MimoClient 处理。
    """

    def parse_response(self, content_blocks: list[dict[str, Any]]) -> ParsedResponse:
        """解析 SDK 返回的 content_blocks，提取文本和工具调用。

        Args:
            content_blocks: SDK 返回的 content blocks 列表。

        Returns:
            ParsedResponse: 解析后的文本和工具调用。
        """
        ...

    def supports_native_tools(self) -> bool:
        """是否支持原生 tool_use 格式。

        支持原生格式的模型，SDK 会直接返回结构化的工具调用块，
        不需要从文本中解析。
        """
        ...
