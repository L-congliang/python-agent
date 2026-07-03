"""搜索工具 - 让 Agent 能够搜索文件内容

对齐 Claude Code 的 Grep 工具实现。
使用 ripgrep 作为底层搜索引擎。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from agent.core.context import ToolUseContext
from agent.core.types import ToolResult, ValidationResult
from agent.tools.base import build_tool


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


def _build_rg_command(
    pattern: str,
    path: str,
    include: str | None,
    max_results: int,
    case_sensitive: bool,
    context_lines: int,
) -> list[str]:
    """构造 ripgrep 命令参数

    Args:
        pattern: 搜索模式（正则）
        path: 搜索路径
        include: 文件过滤（glob 模式）
        max_results: 最大结果数
        case_sensitive: 大小写敏感
        context_lines: 上下文行数

    Returns:
        命令参数列表
    """
    cmd = [
        "rg",
        "--line-number",
        "--with-filename",
        "--no-heading",
        "--max-count",
        str(max_results),
    ]

    if case_sensitive:
        cmd.append("--case-sensitive")
    else:
        cmd.append("--case-insensitive")

    if include:
        cmd.extend(["--glob", include])

    if context_lines > 0:
        cmd.extend(["--context", str(context_lines)])

    cmd.append(pattern)
    cmd.append(path)

    return cmd


def _parse_rg_output(output: str) -> list[dict[str, Any]]:
    """解析 ripgrep 输出

    Args:
        output: ripgrep 的原始输出

    Returns:
        解析后的结果列表，每个结果包含 file、line、content
    """
    results = []
    for line in output.strip().split("\n"):
        if not line:
            continue
        # 格式：文件名:行号:内容
        parts = line.split(":", 2)
        if len(parts) == 3:
            try:
                results.append({
                    "file": parts[0],
                    "line": int(parts[1]),
                    "content": parts[2],
                })
            except ValueError:
                # 行号解析失败，跳过该行
                continue
    return results


# ============================================================
# 输入校验
# ============================================================


def validate_grep_input(
    raw_input: dict[str, Any], context: ToolUseContext
) -> ValidationResult:
    """校验 grep 输入

    校验规则:
    1. pattern 必须存在、是字符串且非空
    2. max_results 必须是正整数
    3. context_lines 必须是非负整数
    4. path 如果提供，必须是非空字符串且路径存在

    Args:
        raw_input: 工具输入
        context: 工具执行上下文

    Returns:
        ValidationResult
    """
    # 检查 pattern
    pattern = raw_input.get("pattern")
    if not pattern or not isinstance(pattern, str) or not pattern.strip():
        return ValidationResult.failure("pattern 不能为空")

    # 检查 max_results
    max_results = raw_input.get("max_results", DEFAULT_MAX_RESULTS)
    if not isinstance(max_results, int) or max_results < 1:
        return ValidationResult.failure("max_results 必须是正整数")

    # 检查 context_lines
    context_lines = raw_input.get("context_lines", 0)
    if not isinstance(context_lines, int) or context_lines < 0:
        return ValidationResult.failure("context_lines 必须是非负整数")

    # 检查 path（如果提供）
    path = raw_input.get("path")
    if path is not None:
        if not isinstance(path, str) or not path.strip():
            return ValidationResult.failure("path 不能为空字符串")
        abs_path = _resolve_path(path, context.cwd)
        if not os.path.exists(abs_path):
            return ValidationResult.failure(f"路径不存在: {abs_path}")

    return ValidationResult.success()


# ============================================================
# 核心逻辑
# ============================================================


def execute_grep(input: dict[str, Any], context: ToolUseContext) -> ToolResult:
    """执行 grep 搜索

    使用 ripgrep 搜索文件内容，返回匹配的行。

    Args:
        input: 工具输入参数，包含 pattern、path、include 等
        context: 工具执行上下文

    Returns:
        ToolResult: 搜索结果或错误信息
    """
    # 检查 ripgrep 是否安装
    if not _check_ripgrep_installed():
        return ToolResult(
            output="ripgrep 未安装。请安装 ripgrep：\n"
                   "  Windows: winget install BurntSushi.ripgrep.MSVC\n"
                   "  Mac: brew install ripgrep\n"
                   "  Linux: sudo apt install ripgrep",
            is_error=True,
        )

    # 检查中断
    if context.abort_controller.is_aborted:
        return ToolResult(output="搜索被取消", is_error=True)

    # 解析参数
    pattern: str = input.get("pattern", "")
    path = input.get("path", context.cwd)
    include = input.get("include")
    max_results = input.get("max_results", DEFAULT_MAX_RESULTS)
    case_sensitive = input.get("case_sensitive", False)
    context_lines = input.get("context_lines", 0)

    # 解析路径
    abs_path = _resolve_path(path, context.cwd)

    # 检查路径存在性
    if not os.path.exists(abs_path):
        return ToolResult(output=f"路径不存在: {abs_path}", is_error=True)

    try:
        # 构造命令
        cmd = _build_rg_command(
            pattern=pattern,
            path=abs_path,
            include=include,
            max_results=max_results,
            case_sensitive=case_sensitive,
            context_lines=context_lines,
        )

        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 处理结果
        if result.returncode == 0:
            # 有匹配结果
            results = _parse_rg_output(result.stdout)
            if not results:
                return ToolResult(output="No matches found", is_error=False)

            # 格式化输出
            output_lines = []
            for r in results:
                output_lines.append(f"{r['file']}:{r['line']}:{r['content']}")
            return ToolResult(output="\n".join(output_lines), is_error=False)

        elif result.returncode == 1:
            # 无匹配结果（ripgrep 返回 1 表示无匹配）
            return ToolResult(output="No matches found", is_error=False)

        else:
            # 错误
            return ToolResult(
                output=f"搜索失败: {result.stderr}",
                is_error=True,
            )

    except subprocess.TimeoutExpired:
        return ToolResult(output="搜索超时（30秒）", is_error=True)
    except Exception as e:
        return ToolResult(output=f"搜索失败: {str(e)}", is_error=True)


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


# ============================================================
# 工具注册
# ============================================================

grep_tool = build_tool(
    name="grep",
    description="搜索文件内容。支持正则表达式、文件过滤、路径指定等。优先于 bash grep 使用。",
    parameters=GREP_PARAMETERS,
    execute_fn=execute_grep,
    is_read_only=lambda input: True,
    is_concurrency_safe=lambda input: True,
    validate_input=validate_grep_input,
    get_summary=lambda input: f"Searching for '{input.get('pattern', '')}'",
    get_user_facing_name=lambda input: "Grep",
    get_activity_description=lambda input: f"Searching for '{input.get('pattern', '')}'",
)
