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
        # 文件不存在，检查目录权限
        directory = os.path.dirname(file_path)
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
