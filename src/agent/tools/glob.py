"""文件发现工具 - 让 Agent 能够按模式匹配文件路径

对齐 Claude Code 的 Glob 工具实现。
使用 pathlib.Path.glob() 进行模式匹配。
"""

from __future__ import annotations

import os
import pathlib
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


def _get_file_mtime(path: str) -> float:
    """获取文件修改时间

    Args:
        path: 文件路径

    Returns:
        修改时间戳（秒），文件不存在时返回 0.0
    """
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _sort_results(paths: list[str], sort_by: str) -> list[str]:
    """排序文件路径列表

    Args:
        paths: 文件路径列表
        sort_by: 排序方式，"modified"（按修改时间降序）或 "path"（按路径字母序）

    Returns:
        排序后的路径列表
    """
    if not paths:
        return []

    if sort_by == "path":
        return sorted(paths)
    # 默认按修改时间降序（最新修改的在前）
    return sorted(paths, key=_get_file_mtime, reverse=True)


# ============================================================
# 输入校验
# ============================================================


def validate_glob_input(
    raw_input: dict[str, Any], context: ToolUseContext
) -> ValidationResult:
    """校验 glob 输入

    校验规则:
    1. pattern 必须存在、是字符串且非空
    2. path 如果提供，必须是非空字符串且路径存在
    3. max_results 如果提供，必须是正整数
    4. sort_by 如果提供，必须是 "modified" 或 "path"

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

    # 检查 path（如果提供）
    path = raw_input.get("path")
    if path is not None:
        if not isinstance(path, str) or not path.strip():
            return ValidationResult.failure("path 不能为空字符串")
        abs_path = _resolve_path(path, context.cwd)
        if not os.path.exists(abs_path):
            return ValidationResult.failure(f"路径不存在: {abs_path}")

    # 检查 max_results
    max_results = raw_input.get("max_results", DEFAULT_MAX_RESULTS)
    if not isinstance(max_results, int) or max_results < 1:
        return ValidationResult.failure("max_results 必须是正整数")

    # 检查 sort_by
    sort_by = raw_input.get("sort_by", "modified")
    if sort_by not in ("modified", "path"):
        return ValidationResult.failure('sort_by 必须是 "modified" 或 "path"')

    return ValidationResult.success()


# ============================================================
# 核心逻辑
# ============================================================


def execute_glob(input: dict[str, Any], context: ToolUseContext) -> ToolResult:
    """执行 glob 文件搜索

    使用 pathlib.Path.glob() 按模式匹配文件路径。

    Args:
        input: 工具输入参数，包含 pattern、path、max_results、sort_by
        context: 工具执行上下文

    Returns:
        ToolResult: 文件路径列表或错误信息
    """
    # 检查中断
    if context.abort_controller.is_aborted:
        return ToolResult(output="搜索被取消", is_error=True)

    # 解析参数
    pattern: str = input.get("pattern", "")
    path = input.get("path", context.cwd)
    max_results = input.get("max_results", DEFAULT_MAX_RESULTS)
    sort_by = input.get("sort_by", "modified")

    # 解析路径
    abs_path = _resolve_path(path, context.cwd)

    # 检查路径存在性
    if not os.path.exists(abs_path):
        return ToolResult(output=f"路径不存在: {abs_path}", is_error=True)

    try:
        # 执行 glob 匹配
        base = pathlib.Path(abs_path)
        matched = list(base.glob(pattern))

        # 只保留文件（排除目录）
        files = [str(p) for p in matched if p.is_file()]

        # 排序
        files = _sort_results(files, sort_by)

        # 截断
        total = len(files)
        files = files[:max_results]

        if not files:
            return ToolResult(output="No files found", is_error=False)

        # 格式化输出
        output_lines = files + [f"\n(共 {total} 个文件)"]
        return ToolResult(output="\n".join(output_lines), is_error=False)

    except ValueError as e:
        # pattern 无效
        return ToolResult(output=f"无效的 glob 模式: {e}", is_error=True)
    except Exception as e:
        return ToolResult(output=f"搜索失败: {e}", is_error=True)


# ============================================================
# 参数定义
# ============================================================

GLOB_PARAMETERS = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "glob 模式，如 **/*.py、src/**/*.ts",
        },
        "path": {
            "type": "string",
            "description": "搜索路径（绝对或相对路径），默认当前工作目录",
        },
        "max_results": {
            "type": "integer",
            "description": "最大结果数，默认 100",
            "default": DEFAULT_MAX_RESULTS,
        },
        "sort_by": {
            "type": "string",
            "enum": ["modified", "path"],
            "description": "排序方式，默认 modified（按修改时间降序）",
            "default": "modified",
        },
    },
    "required": ["pattern"],
}


# ============================================================
# 工具注册
# ============================================================

glob_tool = build_tool(
    name="glob",
    description="按模式匹配查找文件路径。支持递归 glob 模式如 **/*.py。",
    parameters=GLOB_PARAMETERS,
    execute_fn=execute_glob,
    is_read_only=lambda input: True,
    is_concurrency_safe=lambda input: True,
    validate_input=validate_glob_input,
    get_summary=lambda input: f"Glob: {input.get('pattern', '')}",
    get_user_facing_name=lambda input: "Glob",
    get_activity_description=lambda input: f"Searching files: {input.get('pattern', '')}",
)
