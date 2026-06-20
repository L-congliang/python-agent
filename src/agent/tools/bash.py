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


# ============================================================
# 输入校验
# ============================================================


def validate_bash_input(raw_input: dict, context: ToolUseContext) -> ValidationResult:
    """校验 bash 命令输入

    校验规则:
    1. command 必须存在且非空
    2. timeout 必须是正数
    3. workdir 如果指定，必须是绝对路径

    Args:
        raw_input: 工具调用的原始输入参数
        context: 工具执行上下文（预留，未来用于检查 blocked commands 等）

    Returns:
        ValidationResult: 校验结果
    """
    _ = context  # 预留：未来用于检查 blocked commands 等
    command = raw_input.get("command")
    if not command or not isinstance(command, str) or not command.strip():
        return ValidationResult.failure("command 不能为空")

    timeout = raw_input.get("timeout", 30)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        return ValidationResult.failure("timeout 必须是正数")

    workdir = raw_input.get("workdir")
    if workdir is not None:
        if not isinstance(workdir, str) or not os.path.isabs(workdir):
            return ValidationResult.failure("workdir 必须是绝对路径")

    return ValidationResult.success()


# ============================================================
# 命令执行
# ============================================================


def execute_bash(input: dict, context: ToolUseContext) -> ToolResult:
    """执行 bash 命令

    Args:
        input: {"command": "ls -la", "timeout": 30, "workdir": "/tmp"}
        context: 工具执行上下文

    Returns:
        ToolResult: 包含 stdout/stderr 的结果
    """
    command = input["command"]
    timeout = input.get("timeout", 30)
    workdir = input.get("workdir") or context.cwd

    # 检查中断
    if context.abort_controller.is_aborted:
        return ToolResult(output="命令执行被取消", is_error=True)

    # 检测 shell
    shell_exe, shell_arg = _detect_shell()

    # 确保 workdir 是绝对路径（context.cwd 可能是 "."）
    if workdir and not os.path.isabs(workdir):
        workdir = os.path.abspath(workdir)

    try:
        # 使用 subprocess.run 执行（列表参数，自己控制 shell）
        result = subprocess.run(
            [shell_exe, shell_arg, command],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )

        # 格式化输出
        output_parts = []
        if result.stdout:
            stdout = _truncate_output(result.stdout)
            output_parts.append(stdout)
        if result.stderr:
            output_parts.append(f"\n[stderr]\n{result.stderr}")
        output_parts.append(f"\n[exit code: {result.returncode}]")

        output = "".join(output_parts)
        is_error = result.returncode != 0

        return ToolResult(output=output, is_error=is_error)

    except subprocess.TimeoutExpired:
        return ToolResult(
            output=f"命令超时（超过 {timeout} 秒）",
            is_error=True,
        )
    except Exception as e:
        return ToolResult(
            output=f"命令执行失败: {str(e)}",
            is_error=True,
        )
