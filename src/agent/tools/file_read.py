"""文件读取工具 - 让 Agent 能够读取文件内容

对齐 Claude Code 的 Read 工具实现。
支持文本文件和 Jupyter Notebook。
"""

from __future__ import annotations

import json
import os
from typing import Any

import chardet

from agent.core.context import ToolUseContext
from agent.core.types import ToolResult, ValidationResult
from agent.tools.base import build_tool
from agent.tools.observation_helper import build_observation


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


def _read_notebook(file_path: str, offset: int, limit: int) -> str:
    """读取 Jupyter Notebook 并格式化为可读文本

    Args:
        file_path: Notebook 文件路径
        offset: 起始行号
        limit: 读取行数

    Returns:
        格式化后的内容（已应用行号和截断）
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            notebook = json.load(f)
    except json.JSONDecodeError as e:
        return f"无效的 Notebook 格式（JSON 解析失败）: {file_path}\n{e}"

    cells = notebook.get("cells", [])
    output_lines = []

    for i, cell in enumerate(cells):
        cell_type = cell.get("cell_type", "unknown")
        source = "".join(cell.get("source", []))

        # 添加 cell 分隔线
        output_lines.append(f"--- Cell {i + 1} ({cell_type}) ---")

        # 添加 cell 内容
        if source:
            output_lines.append(source.rstrip())

        # code cell 的输出
        if cell_type == "code":
            for output in cell.get("outputs", []):
                text_parts = output.get("text", [])
                if text_parts:
                    text = "".join(text_parts).rstrip()
                    if text:
                        output_lines.append(f"--- Cell {i + 1} Output ---")
                        output_lines.append(text)

        output_lines.append("")  # cell 之间空行

    content = "\n".join(output_lines)

    # 应用 offset/limit
    lines = content.split("\n")
    start = offset - 1
    end = start + limit
    selected_lines = lines[start:end]
    selected_content = "\n".join(selected_lines)

    return _format_with_line_numbers(selected_content, start_line=offset)


# ============================================================
# 参数定义
# ============================================================

FILE_READ_PARAMETERS = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "要读取的文件路径（绝对路径或相对于 cwd 的路径）",
        },
        "offset": {
            "type": "integer",
            "description": "起始行号（从 1 开始），默认 1",
            "default": 1,
        },
        "limit": {
            "type": "integer",
            "description": "读取的行数，默认 2000",
            "default": 2000,
        },
    },
    "required": ["file_path"],
}


# ============================================================
# 文件读取核心逻辑
# ============================================================


def _read_file_content(file_path: str) -> str:
    """读取文件原始内容（检测编码后解码）

    Args:
        file_path: 文件绝对路径

    Returns:
        文件内容字符串
    """
    encoding = _detect_encoding(file_path)
    with open(file_path, encoding=encoding) as f:
        return f.read()


def _read_file_with_cache(file_path: str, context: ToolUseContext) -> str:
    """读取文件，带 FileReadState 缓存 + mtime 检查

    Args:
        file_path: 文件绝对路径
        context: 工具执行上下文

    Returns:
        文件内容字符串
    """
    current_mtime = os.path.getmtime(file_path)
    cached = context.file_read_state.get(file_path)

    if cached is not None:
        cached_content, cached_mtime = cached
        if cached_mtime == current_mtime:
            return cached_content

    content = _read_file_content(file_path)
    context.file_read_state.set(file_path, content, current_mtime)
    return content


def execute_file_read(input: dict[str, Any], context: ToolUseContext) -> ToolResult:
    """读取文件内容

    Args:
        input: {"file_path": "src/main.py", "offset": 1, "limit": 2000}
        context: 工具执行上下文

    Returns:
        ToolResult: 带行号的文件内容
    """
    file_path = input.get("file_path")
    if not file_path or not isinstance(file_path, str) or not file_path.strip():
        return ToolResult(output="file_path 不能为空", is_error=True)
    offset = input.get("offset", 1)
    limit = input.get("limit", MAX_LINES)

    # 检查中断
    if context.abort_controller.is_aborted:
        return ToolResult(output="文件读取被取消", is_error=True)

    # 解析路径
    abs_path = _resolve_path(file_path, context.cwd)

    # 检查文件存在性
    if not os.path.exists(abs_path):
        return ToolResult(output=f"文件不存在: {abs_path}", is_error=True)

    # 检查是否是目录
    if os.path.isdir(abs_path):
        return ToolResult(output=f"路径是目录，不是文件: {abs_path}", is_error=True)

    try:
        # 检查是否是 Notebook
        if abs_path.endswith(".ipynb"):
            result = _read_notebook(abs_path, offset, limit)
            return ToolResult(output=result, is_error=False)

        # 带缓存读取（文本文件）
        content = _read_file_with_cache(abs_path, context)

        # 先应用 offset/limit 到原始内容（selected_content 是完整切片，不截断）
        lines = content.split("\n")
        start = offset - 1  # offset 从 1 开始，转为 0-based index
        end = start + limit
        selected_content = "\n".join(lines[start:end])

        # 添加行号（完整切片）
        full_output = _format_with_line_numbers(selected_content, start_line=offset)

        # Observation Budget 契约：统一截断（file_read 保留头部）
        # output 保持完整（full_output），observation.preview 是截断版本
        preview, observation = build_observation(
            output=full_output,
            tool_name="read",
            artifact_dir=context.artifact_dir,
            strategy="head",  # file_read 保留头部
        )

        return ToolResult(
            output=full_output,  # output 是完整切片（向后兼容）
            is_error=False,
            observation=observation,  # observation.preview 是截断版本
        )

    except UnicodeDecodeError:
        return ToolResult(
            output=f"无法解码文件（编码不支持）: {abs_path}",
            is_error=True,
        )
    except Exception as e:
        return ToolResult(
            output=f"文件读取失败: {str(e)}",
            is_error=True,
        )


def validate_file_read_input(raw_input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
    """校验文件读取输入

    Args:
        raw_input: 工具输入
        context: 工具执行上下文

    Returns:
        ValidationResult
    """
    file_path = raw_input.get("file_path")
    if not file_path or not isinstance(file_path, str) or not file_path.strip():
        return ValidationResult.failure("file_path 不能为空")

    offset = raw_input.get("offset", 1)
    if not isinstance(offset, int) or offset < 1:
        return ValidationResult.failure("offset 必须是正整数")

    limit = raw_input.get("limit", MAX_LINES)
    if not isinstance(limit, int) or limit < 1:
        return ValidationResult.failure("limit 必须是正整数")

    # 检查文件存在性
    abs_path = _resolve_path(file_path, context.cwd)
    if not os.path.exists(abs_path):
        return ValidationResult.failure(f"文件不存在: {abs_path}")

    if os.path.isdir(abs_path):
        return ValidationResult.failure(f"路径是目录，不是文件: {abs_path}")

    return ValidationResult.success()


# ============================================================
# 工具注册
# ============================================================

file_read_tool = build_tool(
    name="read",
    description="读取文件内容。支持文本文件和 Jupyter Notebook。可指定行范围（offset/limit）。",
    parameters=FILE_READ_PARAMETERS,
    execute_fn=execute_file_read,
    is_read_only=lambda input: True,
    is_concurrency_safe=lambda input: True,
    validate_input=validate_file_read_input,
    get_summary=lambda input: f"Reading {os.path.basename(input.get('file_path', ''))}",
    get_user_facing_name=lambda input: "Read",
    get_activity_description=lambda input: f"Reading {input.get('file_path', '')}",
)
