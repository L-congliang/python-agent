"""DeepSeek 模型适配器。

DeepSeek 的特点：
- 使用 Anthropic 兼容 API
- 返回扩展思考内容（ThinkingBlock），需要跳过
- 工具调用以 HTML 文本形式输出（如 ✿FUNCTION✿: bash）
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..model_adapter import ModelAdapter, ParsedResponse, ToolCall

logger = logging.getLogger(__name__)


class DeepSeekAdapter(ModelAdapter):
    """DeepSeek 模型适配器。

    封装 DeepSeek 特有的响应解析：
    - 跳过 ThinkingBlock，只提取 TextBlock
    - 解析 HTML 格式的工具调用（✿FUNCTION✿ 等标记）
    """

    def supports_native_tools(self) -> bool:
        """DeepSeek 的原生 tool_use 支持待确认。

        目前返回 False，使用文本解析方式。
        """
        return False

    def parse_response(self, content_blocks: list[dict[str, Any]]) -> ParsedResponse:
        """解析 DeepSeek 的响应。

        DeepSeek 的 content_blocks 可能包含：
        - ThinkingBlock: 扩展思考（跳过）
        - TextBlock: 实际回答（提取）
        - ToolUseBlock: 原生工具调用（如果支持）
        """
        # 提取文本和原生工具调用
        text = ""
        native_tool_calls = []

        for block in content_blocks:
            block_type = block.get("type")
            if block_type == "text":
                if not text:  # 只取第一个 TextBlock
                    text = block.get("text", "")
            elif block_type == "tool_use":
                native_tool_calls.append(ToolCall(
                    name=block.get("name", ""),
                    arguments=block.get("input", {}),
                ))
            # ThinkingBlock 或其他类型，跳过

        # 优先使用原生工具调用
        if native_tool_calls:
            return ParsedResponse(text=text, tool_calls=native_tool_calls)

        # 否则从文本中解析 HTML 格式的工具调用
        tool_calls = self._parse_tool_calls(text)
        return ParsedResponse(text=text, tool_calls=tool_calls)

    def _parse_tool_calls(self, text: str) -> list[ToolCall]:
        """解析 DeepSeek 输出中的工具调用。

        DeepSeek 使用 HTML 格式：
        ✿FUNCTION✿: bash
        ✿FUNCTION✿: bash
        {"command": "ls -la", "timeout": 30000}
        """
        tool_calls = []

        # 匹配 ✿FUNCTION✿: tool_name 后面跟 JSON 参数
        pattern = r"✿FUNCTION✿:\s*(\w+)\s*\n\s*✿FUNCTION✿:\s*\w+\s*\n\s*(\{.*?\})"
        matches = re.findall(pattern, text, re.DOTALL)

        for tool_name, args_text in matches:
            try:
                arguments = json.loads(args_text)
                tool_calls.append(ToolCall(name=tool_name, arguments=arguments))
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse tool arguments: %s", e)
                continue

        # 简化模式（只有一行 ✿FUNCTION✿）
        if not tool_calls:
            simple_pattern = r"✿FUNCTION✿:\s*(\w+)\s*\n\s*(\{.*?\})"
            matches = re.findall(simple_pattern, text, re.DOTALL)
            for tool_name, args_text in matches:
                try:
                    arguments = json.loads(args_text)
                    tool_calls.append(ToolCall(name=tool_name, arguments=arguments))
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse tool arguments: %s", e)
                    continue

        return tool_calls
