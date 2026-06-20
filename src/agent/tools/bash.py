"""Bash 工具 - 让 Agent 能够执行 shell 命令

对齐 Claude Code 的 BashTool 实现。
使用 subprocess.run + shell 检测（Git Bash 优先）+ 输出截断。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Any

from agent.core.context import ToolUseContext
from agent.core.types import ToolResult, ValidationResult
from agent.tools.base import build_tool


# ============================================================
# Shell 检测
# ============================================================

# 缓存检测结果，整个进程只检测一次
_shell_cache: tuple[str, str] | None = None


def _detect_shell() -> tuple[str, str]:
    """检测可用 shell，返回 (executable, arg_prefix)

    优先级：
    1. Git Bash (bash.exe) — 开发者最熟悉的环境，命令和 Linux 一致
    2. cmd.exe (Windows fallback) — 保底可用
    3. /bin/sh (Linux/Mac) — 标准 POSIX shell

    结果缓存，整个进程生命周期只检测一次。
    """
    global _shell_cache
    if _shell_cache is not None:
        return _shell_cache

    # 优先找 bash（Git Bash 或系统自带）
    bash = shutil.which("bash")
    if bash:
        _shell_cache = (bash, "-c")
        return _shell_cache

    # Windows fallback: cmd.exe
    if sys.platform == "win32":
        _shell_cache = ("cmd.exe", "/c")
        return _shell_cache

    # Linux/Mac: /bin/sh
    _shell_cache = ("/bin/sh", "-c")
    return _shell_cache


# ============================================================
# 输出截断
# ============================================================

MAX_OUTPUT_LINES = 2000


def _truncate_output(output: str, max_lines: int = MAX_OUTPUT_LINES) -> str:
    """截断过长的输出，保留尾部

    为什么保留尾部而不是头部？
    - 大多数命令的有用信息在最后（测试结果、错误信息）
    - ls 的文件列表头部是 . 和 ..，尾部才是新增文件
    """
    lines = output.split('\n')
    if len(lines) <= max_lines:
        return output

    truncated = lines[-max_lines:]
    header = f"... (truncated {len(lines) - max_lines} lines)\n"
    return header + '\n'.join(truncated)
