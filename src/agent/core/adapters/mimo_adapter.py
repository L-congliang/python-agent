"""mimo 模型适配器。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..model_adapter import ModelAdapter, ParsedResponse, ToolCall

logger = logging.getLogger(__name__)


class MimoAdapter(ModelAdapter):
    """mimo 模型适配器。"""

    def supports_native_tools(self) -> bool:
        return False

    def parse_response(self, content_blocks: list[dict[str, Any]]) -> ParsedResponse:
        text_parts: list[str] = []
        native_tool_calls: list[ToolCall] = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                native_tool_calls.append(ToolCall(name=block.get("name",""), arguments=block.get("input",{})))
        text = "".join(text_parts)
        if native_tool_calls:
            return ParsedResponse(text=text, tool_calls=native_tool_calls)
        return ParsedResponse(text=text, tool_calls=self._parse_tool_calls(text))

    def _parse_tool_calls(self, text: str) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        for name, params in re.findall(r"<function=(\w+)>(.*?)</function>", text, re.DOTALL):
            tool_calls.append(ToolCall(name=name, arguments=self._parse_eq_params(params)))
        if tool_calls: return tool_calls

        for name, params in re.findall(r"<function_(\w+)>(.*?)</function_\1>", text, re.DOTALL):
            tool_calls.append(ToolCall(name=name, arguments=self._parse_anthropic_params(params)))
        if tool_calls: return tool_calls

        for m in re.findall(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL):
            c = m.strip()
            if c.startswith("{"):
                d = json.loads(c)
                if d.get("name"): tool_calls.append(ToolCall(name=d["name"], arguments=d.get("args",d.get("arguments",{}))))
                continue
            nm = re.search(r"<tool_name>(.*?)</tool_name>", c, re.DOTALL)
            if nm:
                am = re.search(r"<arguments>(.*?)</arguments>", c, re.DOTALL)
                tool_calls.append(ToolCall(name=nm.group(1).strip(), arguments=self._parse_xml_arguments(am.group(1)) if am else {}))
        return tool_calls

    def _parse_eq_params(self, params_text: str) -> dict[str, Any]:
        pattern = r"<parameter=(\w+)>(.*?)</parameter>"
        arguments: dict[str, Any] = {}
        for key, value in re.findall(pattern, params_text.strip(), re.DOTALL):
            try: arguments[key] = json.loads(value.strip())
            except json.JSONDecodeError: arguments[key] = value.strip()
        if not arguments and params_text.strip().startswith("{"):
            try: return dict(json.loads(params_text.strip()))
            except json.JSONDecodeError: pass
        return arguments

    def _parse_anthropic_params(self, params_text: str) -> dict[str, Any]:
        t = params_text.strip()
        if not t: return {}
        if t.startswith("{"):
            try: return dict(json.loads(t))
            except json.JSONDecodeError: pass
        return self._parse_xml_arguments(t)

    def _parse_xml_arguments(self, xml_text: str) -> dict[str, Any]:
        arguments: dict[str, Any] = {}
        for key, value in re.findall(r"<parameter=(\w+)>(.*?)</parameter>", xml_text, re.DOTALL):
            try: arguments[key] = json.loads(value.strip())
            except json.JSONDecodeError: arguments[key] = value.strip()
        if arguments: return arguments
        for key, value in re.findall(r"<(\w+)>(.*?)</\1>", xml_text, re.DOTALL):
            try: arguments[key] = json.loads(value.strip())
            except json.JSONDecodeError: arguments[key] = value.strip()
        return arguments
