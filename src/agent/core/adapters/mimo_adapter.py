"""mimo 模型适配器。

mimo 的特点：
- 使用 Anthropic 兼容 API
- 不使用原生 tool_use，工具调用以 XML 文本形式输出
- 取回答文本直接用 content[0].text
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..model_adapter import ModelAdapter, ParsedResponse, ToolCall

logger = logging.getLogger(__name__)


class MimoAdapter(ModelAdapter):
    """mimo 模型适配器。

    封装 mimo 特有的响应解析：
    - 从 content_blocks 中提取 TextBlock 的文本
    - 从文本中解析 <tool_call> XML 标签
    """

    def supports_native_tools(self) -> bool:
        """mimo 不使用原生 tool_use 格式。"""
        return False

    def parse_response(self, content_blocks: list[dict[str, Any]]) -> ParsedResponse:
        """解析 mimo 的响应。

        mimo 的 content_blocks 可能包含：
        - TextBlock: 文本回答
        - ToolUseBlock: 原生工具调用（如果模型支持）

        如果有原生 tool_use 块，直接使用；否则从文本中解析 XML。
        """
        # 提取文本和原生工具调用
        text_parts = []
        native_tool_calls = []

        for block in content_blocks:
            block_type = block.get("type")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "tool_use":
                # 原生工具调用格式
                native_tool_calls.append(ToolCall(
                    name=block.get("name", ""),
                    arguments=block.get("input", {}),
                ))

        text = "".join(text_parts)

        # 优先使用原生工具调用
        if native_tool_calls:
            return ParsedResponse(text=text, tool_calls=native_tool_calls)

        # 否则从文本中解析 XML 格式的工具调用
        tool_calls = self._parse_tool_calls(text)
        return ParsedResponse(text=text, tool_calls=tool_calls)

    def _parse_tool_calls(self, text: str) -> list[ToolCall]:
        """解析 mimo 输出中的工具调用。

        mimo 使用 XML 格式：
        <tool_call>
        <tool_name>bash</tool_name>
        <arguments>
        <command>ls -la</command>
        </arguments>
        </tool_call>
        """
        tool_calls = []
        pattern = r"<tool_call>(.*?)</tool_call>"
        matches = re.findall(pattern, text, re.DOTALL)

        for match in matches:
            try:
                # 提取 tool_name
                name_match = re.search(r"<tool_name>(.*?)</tool_name>", match, re.DOTALL)
                if not name_match:
                    continue
                tool_name = name_match.group(1).strip()

                # 提取 arguments
                args_match = re.search(r"<arguments>(.*?)</arguments>", match, re.DOTALL)
                if args_match:
                    args_text = args_match.group(1).strip()
                    arguments = self._parse_xml_arguments(args_text)
                else:
                    arguments = {}

                tool_calls.append(ToolCall(name=tool_name, arguments=arguments))
            except Exception as e:
                logger.warning("Failed to parse tool call: %s", e)
                continue

        return tool_calls

    def _parse_xml_arguments(self, xml_text: str) -> dict[str, Any]:
        """解析 XML 格式的参数。

        输入: <command>ls -la</command>\n<timeout>30000</timeout>
        输出: {"command": "ls -la", "timeout": 30000}
        """
        arguments = {}
        pattern = r"<(\w+)>(.*?)</\1>"
        matches = re.findall(pattern, xml_text, re.DOTALL)

        for key, value in matches:
            value = value.strip()
            try:
                arguments[key] = json.loads(value)
            except json.JSONDecodeError:
                arguments[key] = value

        return arguments
