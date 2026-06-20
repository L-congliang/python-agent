"""文件读取工具 - 让 Agent 能够读取文件内容

对齐 Claude Code 的 Read 工具实现。
支持文本文件和 Jupyter Notebook。
"""

from __future__ import annotations

import os
from typing import Any

import chardet

from agent.core.context import ToolUseContext
from agent.core.types import ToolResult, ValidationResult
from agent.tools.base import build_tool


# ============================================================
# 常量
# ============================================================

MAX_LINES = 2000


# ============================================================
# 辅助函数
# ============================================================


def _resolve_path(file_path: str, cwd: str) -> str:
    """解析文件路径为绝对路径

    - 绝对路径：直接使用
    - 相对路径：相对于 context.cwd 解析

    Args:
        file_path: 输入路径（绝对或相对）
        cwd: 当前工作目录

    Returns:
        绝对路径字符串
    """
    if os.path.isabs(file_path):
        return file_path
    return os.path.abspath(os.path.join(cwd, file_path))


def _detect_encoding(file_path: str) -> str:
    """检测文件编码

    策略:
    1. 先尝试 UTF-8 读取（快速，覆盖 90% 场景）
    2. UTF-8 失败则用 chardet 检测前 8KB
    3. chardet 置信度 < 0.5 时 fallback 到 latin-1

    Args:
        file_path: 文件路径

    Returns:
        编码名称（如 "utf-8", "gbk", "latin-1"）
    """
    # 先尝试 UTF-8
    try:
        with open(file_path, encoding="utf-8") as f:
            f.read(1024)  # 读一小段测试
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # 用 chardet 检测
    with open(file_path, "rb") as f:
        raw = f.read(8192)
    result = chardet.detect(raw)
    if result["encoding"] and result["confidence"] >= 0.5:
        return result["encoding"]

    # fallback: latin-1（万能编码，不会报错）
    return "latin-1"


def _format_with_line_numbers(content: str, start_line: int = 1) -> str:
    """添加行号，类似 cat -n

    Args:
        content: 原始内容
        start_line: 起始行号（默认 1）

    Returns:
        带行号的内容
    """
    lines = content.split("\n")
    total = len(lines)
    end_line = start_line + total - 1
    width = len(str(end_line))

    result = []
    for i, line in enumerate(lines):
        line_num = start_line + i
        result.append(f"{line_num:>{width}} │ {line}")
    return "\n".join(result)


def _truncate_lines(content: str, max_lines: int = MAX_LINES) -> str:
    """截断过长内容，保留头部

    与 bash 工具的区别:
    - bash 保留尾部（命令输出有用信息在最后）
    - file_read 保留头部（imports、类定义、函数签名在开头）

    Args:
        content: 原始内容
        max_lines: 最大行数（默认 2000）

    Returns:
        截断后的内容
    """
    lines = content.split("\n")
    if len(lines) <= max_lines:
        return content

    truncated = lines[:max_lines]
    total = len(lines)
    header = f"... (truncated, showing first {max_lines} of {total} lines)\n"
    return header + "\n".join(truncated)
