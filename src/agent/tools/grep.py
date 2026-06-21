"""搜索工具 - 让 Agent 能够搜索文件内容

对齐 Claude Code 的 Grep 工具实现。
使用 ripgrep 作为底层搜索引擎。
"""

from __future__ import annotations

import os
import shutil


# ============================================================
# 常量
# ============================================================

DEFAULT_MAX_RESULTS = 100


# ============================================================
# 辅助函数
# ============================================================


def _check_ripgrep_installed() -> bool:
    """检查 ripgrep 是否已安装

    Returns:
        True 如果 ripgrep 已安装，否则 False
    """
    return shutil.which("rg") is not None


def _resolve_path(path: str, cwd: str) -> str:
    """解析路径为绝对路径

    Args:
        path: 输入路径（绝对或相对）
        cwd: 当前工作目录

    Returns:
        绝对路径字符串
    """
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(cwd, path))


# ============================================================
# 参数定义
# ============================================================

GREP_PARAMETERS = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "搜索模式（支持正则表达式）",
        },
        "path": {
            "type": "string",
            "description": "搜索路径（绝对或相对路径），默认整个项目",
        },
        "include": {
            "type": "string",
            "description": "文件过滤（glob 模式，如 *.py、*.ts）",
        },
        "max_results": {
            "type": "integer",
            "description": "最大结果数，默认 100",
            "default": DEFAULT_MAX_RESULTS,
        },
        "case_sensitive": {
            "type": "boolean",
            "description": "大小写敏感，默认 false",
            "default": False,
        },
        "context_lines": {
            "type": "integer",
            "description": "显示匹配行前后的上下文行数，默认 0",
            "default": 0,
        },
    },
    "required": ["pattern"],
}
