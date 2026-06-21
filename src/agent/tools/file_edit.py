"""文件编辑工具 - 让 Agent 能够精确修改文件内容

对齐 Claude Code 的 Edit 工具实现。
基于 old_string/new_string 精确替换。
"""

from __future__ import annotations

import os
from typing import Any

from agent.core.context import ToolUseContext
from agent.core.types import ToolResult, ValidationResult
from agent.tools.base import build_tool
from agent.tools.file_write import _resolve_path, _update_cache


# ============================================================
# 参数定义
# ============================================================

FILE_EDIT_PARAMETERS = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "要修改的文件路径（绝对路径或相对于 cwd 的路径）",
        },
        "old_string": {
            "type": "string",
            "description": "要替换的原始文本（必须在文件中唯一匹配）",
        },
        "new_string": {
            "type": "string",
            "description": "替换后的新文本",
        },
        "replace_all": {
            "type": "boolean",
            "description": "是否替换所有匹配项（默认 false）",
            "default": False,
        },
    },
    "required": ["file_path", "old_string", "new_string"],
}


# ============================================================
# 输入校验
# ============================================================


def validate_file_edit_input(raw_input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
    """校验文件编辑输入

    校验规则:
    1. file_path 必须存在且非空字符串
    2. file_path 必须是字符串类型
    3. old_string 必须存在且是字符串类型
    4. new_string 必须存在且是字符串类型
    5. 解析后的路径必须存在
    6. 解析后的路径必须是文件（不能是目录）
    7. old_string 必须在文件中存在
    8. 如果 replace_all=False，old_string 必须唯一匹配

    Args:
        raw_input: 工具输入
        context: 工具执行上下文

    Returns:
        ValidationResult
    """
    file_path = raw_input.get("file_path")
    if not file_path or not isinstance(file_path, str) or not file_path.strip():
        return ValidationResult.failure("file_path 不能为空")

    old_string = raw_input.get("old_string")
    if old_string is None or not isinstance(old_string, str) or old_string == "":
        return ValidationResult.failure("old_string 不能为空")

    new_string = raw_input.get("new_string")
    if new_string is None or not isinstance(new_string, str) or new_string == "":
        return ValidationResult.failure("new_string 不能为空")

    # 检查文件存在性
    abs_path = _resolve_path(file_path, context.cwd)
    if not os.path.exists(abs_path):
        return ValidationResult.failure(f"文件不存在: {abs_path}")

    if os.path.isdir(abs_path):
        return ValidationResult.failure(f"路径是目录，不是文件: {abs_path}")

    # 读取文件内容
    try:
        with open(abs_path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return ValidationResult.failure(f"读取文件失败: {e}")

    # 检查 old_string 是否存在
    if old_string not in content:
        return ValidationResult.failure(f"old_string 在文件中不存在")

    # 检查唯一性（replace_all=False 时）
    replace_all = raw_input.get("replace_all", False)
    if not replace_all:
        count = content.count(old_string)
        if count > 1:
            return ValidationResult.failure(f"old_string 匹配多个（{count} 个），请提供更精确的 old_string")

    return ValidationResult.success()


# ============================================================
# 核心执行逻辑
# ============================================================


def execute_file_edit(input: dict[str, Any], context: ToolUseContext) -> ToolResult:
    """修改文件内容

    流程:
    1. 解析参数（file_path, old_string, new_string, replace_all）
    2. 解析路径（_resolve_path，相对 → 绝对）
    3. 检查中断状态
    4. 检查文件存在性
    5. 读取文件内容（带缓存）
    6. 查找 old_string 匹配
    7. 校验唯一性（replace_all=False 时）
    8. 执行替换
    9. 写入文件（UTF-8 编码）
    10. 更新缓存（_update_cache）
    11. 返回 ToolResult

    Args:
        input: {
            "file_path": "src/main.py",
            "old_string": "def hello():",
            "new_string": "def hello(name):",
            "replace_all": False
        }
        context: 工具执行上下文

    Returns:
        ToolResult:
        - output: "修改成功" 或错误信息
        - is_error: 修改失败时为 True
    """
    try:
        # 1. 解析参数
        file_path: str = input["file_path"]
        old_string: str = input["old_string"]
        new_string: str = input["new_string"]
        replace_all: bool = input.get("replace_all", False)

        # 2. 解析路径
        abs_path = _resolve_path(file_path, context.cwd)

        # 3. 检查中断
        if context.abort_controller.is_aborted:
            return ToolResult(output="文件编辑被取消", is_error=True)

        # 4. 检查文件存在性
        if not os.path.exists(abs_path):
            return ToolResult(output=f"文件不存在: {abs_path}", is_error=True)

        if os.path.isdir(abs_path):
            return ToolResult(output=f"路径是目录，不是文件: {abs_path}", is_error=True)

        # 5. 读取文件内容
        try:
            with open(abs_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return ToolResult(output=f"读取文件失败: {e}", is_error=True)

        # 6. 查找 old_string 匹配
        if old_string not in content:
            return ToolResult(output="old_string 在文件中不存在", is_error=True)

        # 7. 校验唯一性（replace_all=False 时）
        if not replace_all:
            count = content.count(old_string)
            if count > 1:
                return ToolResult(
                    output=f"old_string 匹配多个（{count} 个），请提供更精确的 old_string",
                    is_error=True,
                )

        # 8. 执行替换
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        # 9. 写入文件
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # 10. 更新缓存
        _update_cache(abs_path, new_content, context)

        return ToolResult(output="修改成功", is_error=False)

    except Exception as e:
        return ToolResult(output=f"编辑失败: {e}", is_error=True)


# ============================================================
# 工具注册
# ============================================================

file_edit_tool = build_tool(
    name="edit",
    description="修改文件内容。基于 old_string/new_string 精确替换。",
    parameters=FILE_EDIT_PARAMETERS,
    execute_fn=execute_file_edit,
    is_read_only=lambda input: False,       # 写操作
    is_concurrency_safe=lambda input: False, # 不并发安全
    validate_input=validate_file_edit_input,
    get_summary=lambda input: f"Editing {input.get('file_path', '')}",
    get_user_facing_name=lambda input: "Edit",
    get_activity_description=lambda input: f"Editing {input.get('file_path', '')}",
)
