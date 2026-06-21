"""文件写入工具 - 让 Agent 能够创建和修改文件内容

对齐 Claude Code 的 Write/Edit 工具实现。
支持文本文件和 Jupyter Notebook。
"""

from __future__ import annotations

import json
import os
from typing import Any

from agent.core.context import ToolUseContext
from agent.core.types import ToolResult, ValidationResult
from agent.tools.base import build_tool


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


def _ensure_directory(file_path: str) -> None:
    """确保父目录存在，不存在则自动创建

    Args:
        file_path: 文件绝对路径

    Raises:
        OSError: 目录创建失败
    """
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def _check_write_permission(file_path: str) -> str | None:
    """检查文件是否可写

    对于不存在的文件，向上遍历目录树找到第一个存在的父目录，
    检查该目录是否可写。

    Args:
        file_path: 文件绝对路径

    Returns:
        None: 可写
        str: 错误信息（不可写）
    """
    if os.path.exists(file_path):
        # 文件存在，检查文件权限
        if not os.access(file_path, os.W_OK):
            return f"文件不可写: {file_path}"
    else:
        # 文件不存在，向上查找第一个存在的父目录
        directory = os.path.dirname(file_path)
        while directory and not os.path.exists(directory):
            parent = os.path.dirname(directory)
            if parent == directory:
                # 已到根目录，停止
                break
            directory = parent
        if directory and not os.access(directory, os.W_OK):
            return f"目录不可写: {directory}"
    return None


def _check_disk_space(file_path: str, content_size: int) -> str | None:
    """检查磁盘空间是否足够

    Args:
        file_path: 文件绝对路径
        content_size: 要写入的内容大小（字节）

    Returns:
        None: 空间足够
        str: 错误信息（空间不足）
    """
    try:
        directory = os.path.dirname(file_path) or "."
        stat = os.statvfs(directory)  # type: ignore[attr-defined]
        free_space = stat.f_bavail * stat.f_frsize
        if content_size > free_space:
            return f"磁盘空间不足: 需要 {content_size} 字节，可用 {free_space} 字节"
    except (OSError, AttributeError):
        # Windows 不支持 statvfs，跳过检查
        pass
    return None


def _update_cache(file_path: str, content: str, context: ToolUseContext) -> None:
    """更新 FileReadState 缓存

    Args:
        file_path: 文件绝对路径
        content: 文件内容
        context: 工具执行上下文
    """
    mtime = os.path.getmtime(file_path)
    context.file_read_state.set(file_path, content, mtime)


# ============================================================
# 参数定义
# ============================================================

FILE_WRITE_PARAMETERS = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "要写入的文件路径（绝对路径或相对于 cwd 的路径）",
        },
        "content": {
            "type": "string",
            "description": "要写入的文件内容（纯文本，不带行号）",
        },
    },
    "required": ["file_path", "content"],
}


# ============================================================
# 输入校验
# ============================================================


def validate_file_write_input(raw_input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
    """校验文件写入输入

    校验规则:
    1. file_path 必须存在且非空字符串
    2. file_path 必须是字符串类型
    3. content 必须存在且是字符串类型
    4. 解析后的路径不能是目录

    Args:
        raw_input: 工具输入
        context: 工具执行上下文

    Returns:
        ValidationResult
    """
    file_path = raw_input.get("file_path")
    if not file_path or not isinstance(file_path, str) or not file_path.strip():
        return ValidationResult.failure("file_path 不能为空")

    content = raw_input.get("content")
    if content is None or not isinstance(content, str):
        return ValidationResult.failure("content 不能为空")

    # 检查路径是否是目录
    abs_path = _resolve_path(file_path, context.cwd)
    if os.path.isdir(abs_path):
        return ValidationResult.failure(f"路径是目录，不是文件: {abs_path}")

    return ValidationResult.success()


# ============================================================
# Notebook 写入
# ============================================================


def _validate_notebook_structure(notebook: dict[str, Any]) -> str | None:
    """验证 Notebook 结构

    Args:
        notebook: Notebook 字典

    Returns:
        None: 有效
        str: 错误信息（无效）
    """
    required_fields = ["cells", "metadata", "nbformat"]
    for field in required_fields:
        if field not in notebook:
            return f"Notebook 缺少 {field} 字段"

    # 验证 cells 是列表
    if not isinstance(notebook["cells"], list):
        return "cells 字段必须是列表"

    # 验证每个 cell 的结构
    for i, cell in enumerate(notebook["cells"]):
        if "cell_type" not in cell:
            return f"Cell {i} 缺少 cell_type 字段"
        if "source" not in cell:
            return f"Cell {i} 缺少 source 字段"

    return None


def _write_notebook(file_path: str, content: str) -> None:
    """写入 Jupyter Notebook

    流程:
    1. 解析 JSON 内容
    2. 验证 Notebook 结构（cells、metadata、nbformat）
    3. 写入文件（UTF-8 编码）

    Args:
        file_path: Notebook 文件路径
        content: Notebook JSON 内容

    Raises:
        ValueError: JSON 格式无效
        ValueError: Notebook 结构无效
    """
    try:
        notebook = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"无效的 JSON 格式: {e}")

    # 验证 Notebook 结构
    validation_error = _validate_notebook_structure(notebook)
    if validation_error:
        raise ValueError(validation_error)

    # 写入文件
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(notebook, f, indent=1, ensure_ascii=False)


# ============================================================
# 核心执行
# ============================================================


def execute_file_write(input: dict[str, Any], context: ToolUseContext) -> ToolResult:
    """写入文件内容

    流程:
    1. 解析参数（file_path, content）
    2. 解析路径（_resolve_path，相对 → 绝对）
    3. 检查中断状态
    4. 检查写权限（_check_write_permission）
    5. 检查磁盘空间（_check_disk_space）
    6. 自动创建父目录（_ensure_directory）
    7. 写入文件（UTF-8 编码）
    8. 更新缓存（_update_cache）
    9. 返回 ToolResult

    Args:
        input: {"file_path": "src/main.py", "content": "..."}
        context: 工具执行上下文

    Returns:
        ToolResult:
        - output: "写入成功" 或错误信息
        - is_error: 写入失败时为 True
    """
    try:
        # 1. 解析参数（校验已通过，此处做类型断言）
        file_path: str = input["file_path"]
        content: str = input["content"]

        # 2. 解析路径
        abs_path = _resolve_path(file_path, context.cwd)

        # 2.5 检查路径是否是目录（避免 Windows 上的 PermissionError）
        if os.path.isdir(abs_path):
            return ToolResult(
                output=f"路径是目录，不是文件: {abs_path}", is_error=True
            )

        # 3. 检查中断
        if context.abort_controller.is_aborted:
            return ToolResult(output="文件写入被取消", is_error=True)

        # 4. 检查写权限
        permission_error = _check_write_permission(abs_path)
        if permission_error:
            return ToolResult(output=permission_error, is_error=True)

        # 5. 检查磁盘空间
        space_error = _check_disk_space(abs_path, len(content.encode("utf-8")))
        if space_error:
            return ToolResult(output=space_error, is_error=True)

        # 6. 自动创建目录
        _ensure_directory(abs_path)

        # 7. 写入文件
        if abs_path.endswith(".ipynb"):
            _write_notebook(abs_path, content)
        else:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)

        # 8. 更新缓存
        _update_cache(abs_path, content, context)

        return ToolResult(output="写入成功", is_error=False)

    except ValueError as e:
        return ToolResult(output=f"输入错误: {e}", is_error=True)
    except OSError as e:
        return ToolResult(output=f"文件系统错误: {e}", is_error=True)
    except Exception as e:
        return ToolResult(output=f"写入失败: {e}", is_error=True)


# ============================================================
# 工具注册
# ============================================================

file_write_tool = build_tool(
    name="write",
    description="写入文件内容。创建新文件或覆盖现有文件。",
    parameters=FILE_WRITE_PARAMETERS,
    execute_fn=execute_file_write,
    is_read_only=lambda input: False,       # 写操作
    is_concurrency_safe=lambda input: False, # 不并发安全
    validate_input=validate_file_write_input,
    get_summary=lambda input: f"Writing {input.get('file_path', '')}",
    get_user_facing_name=lambda input: "Write",
    get_activity_description=lambda input: f"Writing {input.get('file_path', '')}",
)
