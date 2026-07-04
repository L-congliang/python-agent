"""History Formatter - 将消息历史转为结构化摘要

将 AgentLoop 的 _messages: list[dict] 转为结构化摘要字符串，
不保留完整 tool_output，只保留摘要、预览和错误关键信息。

设计决策:
- 为什么独立成模块？
  避免把格式化逻辑塞进 loop.py 或 ContextManager，职责单一，可独立测试。
- 为什么不保留完整 tool_result？
  和记忆区重复（file_summaries 已有文件摘要），且最吃 token 的
  恰恰是 read/bash/grep 输出，会挤压多轮对话上下文。
"""

from __future__ import annotations

import json
from typing import Any

# 预览截断长度
PREVIEW_MAX_SHORT = 150
PREVIEW_MAX_LONG = 250


def format_history(messages: list[dict[str, Any]], max_tokens: int = 4000) -> str:
    """将消息历史转为结构化摘要

    Args:
        messages: 消息列表（Anthropic 格式）
        max_tokens: 最大 token 数（粗估: len(text) // 4）

    Returns:
        结构化摘要字符串
    """
    if not messages:
        return ""

    parts: list[str] = []
    for msg in messages:
        formatted = _format_message(msg)
        if formatted:
            parts.append(formatted)

    result = "\n".join(parts)

    # 从前面截断，保留最近消息
    estimated_tokens = len(result) // 4
    if estimated_tokens > max_tokens:
        # 从后面开始保留
        target_chars = max_tokens * 4
        result = result[-target_chars:]
        # 找第一个换行符，避免截断中间行
        newline_idx = result.find("\n")
        if newline_idx > 0:
            result = result[newline_idx + 1:]
        result = "...(history truncated)...\n" + result

    return result


def _format_message(msg: dict[str, Any]) -> str:
    """格式化单条消息"""
    role = msg.get("role", "")
    content = msg.get("content", "")

    if isinstance(content, str):
        return f"[{role}] {content}"

    if isinstance(content, list):
        parts = []
        for block in content:
            formatted = _format_block(role, block)
            if formatted:
                parts.append(formatted)
        return "\n".join(parts)

    return ""


def _format_block(role: str, block: dict[str, Any]) -> str:
    """格式化单个 content block"""
    block_type = block.get("type", "")

    if block_type == "text":
        text = block.get("text", "")
        return f"[{role}] {text}"

    if block_type == "tool_use":
        name = block.get("name", "")
        inp = block.get("input", {})
        return _format_tool_use(name, inp)

    if block_type == "tool_result":
        return _format_tool_result(block)

    return ""


def _format_tool_use(name: str, inp: dict[str, Any]) -> str:
    """格式化工具调用"""
    if name == "read":
        path = inp.get("file_path", "")
        return f"[tool_use] read path={path}"
    if name in ("grep", "glob"):
        pattern = inp.get("pattern", inp.get("query", ""))
        path = inp.get("path", "")
        return f"[tool_use] {name} pattern={pattern} path={path}"
    if name == "bash":
        cmd = inp.get("command", "")
        return f"[tool_use] bash cmd={cmd}"
    if name in ("write", "edit"):
        path = inp.get("file_path", "")
        return f"[tool_use] {name} path={path}"
    return f"[tool_use] {name}"


def _format_tool_result(block: dict[str, Any]) -> str:
    """格式化工具结果"""
    is_error = block.get("is_error", False)
    content = block.get("content", "")

    if not isinstance(content, str):
        content = str(content)

    if is_error:
        # 失败结果保留完整错误信息
        return f"[tool_result:ERROR] {content}"

    # 成功结果：截断预览
    preview = content[:PREVIEW_MAX_LONG]
    if len(content) > PREVIEW_MAX_LONG:
        preview = preview.rstrip() + "...(truncated)"
    return f"[tool_result] {preview}"
