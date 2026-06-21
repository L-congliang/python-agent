"""权限检查器 - 通用权限策略层

对齐 Claude Code 的权限系统设计：
- 权限模式管理（default、plan）
- 基于工具行为标记的自动策略判断
- 工具级权限委托和决策合并

设计决策：
- 工具级 check_permissions 优先级最高（deny/ask 直接返回，allow 继续检查系统级策略）
- 系统级策略基于 is_read_only/is_destructive + 权限模式
- plan 模式下禁止所有非只读操作（安全第一）
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from agent.core.types import PermissionBehavior, PermissionDecision

if TYPE_CHECKING:
    from agent.core.context import ToolUseContext
    from agent.tools.base import Tool


class PermissionMode(Enum):
    """权限模式

    控制系统级权限策略的严格程度。
    - DEFAULT: 正常模式，非只读操作需要用户确认
    - PLAN: 计划模式，只允许只读操作，禁止所有写入
    """

    DEFAULT = "default"
    PLAN = "plan"


def check_system_policy(
    tool: Tool,
    input_data: dict[str, object],
    mode: PermissionMode,
) -> PermissionDecision:
    """检查系统级权限策略

    基于工具的 is_read_only/is_destructive 标记和权限模式做出决策。

    决策逻辑：
    - default 模式：只读=allow，非只读=ask
    - plan 模式：只读=allow，非只读=deny

    Args:
        tool: 工具实例
        input_data: 工具输入
        mode: 权限模式

    Returns:
        系统级权限决策
    """
    is_read_only = tool.is_read_only(input_data)
    tool_name = tool.name

    if mode == PermissionMode.PLAN:
        # 计划模式：只允许只读操作
        if is_read_only:
            return PermissionDecision.allow()
        return PermissionDecision.deny(
            f"计划模式下禁止执行非只读工具 '{tool_name}'"
        )

    # default 模式
    if is_read_only:
        return PermissionDecision.allow()

    # 非只读操作需要用户确认
    is_destructive = tool.is_destructive(input_data)
    if is_destructive:
        return PermissionDecision.ask(
            f"工具 '{tool_name}' 将执行破坏性操作，是否确认？"
        )
    return PermissionDecision.ask(
        f"工具 '{tool_name}' 将执行写入操作，是否确认？"
    )


class PermissionChecker:
    """权限检查器

    管理权限模式和自动策略判断。合并工具级决策和系统级策略。

    决策优先级：
    1. 工具级 check_permissions（deny/ask 直接返回）
    2. 系统级策略（基于 is_read_only/is_destructive + 权限模式）
    """

    def __init__(self, mode: PermissionMode = PermissionMode.DEFAULT) -> None:
        """初始化权限检查器。

        Args:
            mode: 权限模式
        """
        self._mode = mode

    @property
    def mode(self) -> PermissionMode:
        """当前权限模式。"""
        return self._mode

    def set_mode(self, mode: PermissionMode) -> None:
        """切换权限模式。

        Args:
            mode: 新的权限模式
        """
        self._mode = mode

    def check(
        self,
        tool: Tool,
        input_data: dict[str, object],
        context: ToolUseContext,
    ) -> PermissionDecision:
        """检查工具是否有权限执行。

        执行流程：
        1. 调用工具的 check_permissions 获取工具级决策
        2. 如果工具级决策是 deny/ask，直接返回
        3. 如果工具级决策是 allow，检查系统级策略
        4. 返回最终决策

        Args:
            tool: 工具实例
            input_data: 工具输入
            context: 工具执行上下文

        Returns:
            最终的权限决策
        """
        # 1. 工具级权限检查
        tool_decision = tool.check_permissions(input_data, context)

        # 2. 工具级 deny/ask 优先
        if tool_decision.behavior in (PermissionBehavior.DENY, PermissionBehavior.ASK):
            return tool_decision

        # 3. 工具级 allow，检查系统级策略
        system_decision = check_system_policy(tool, input_data, self._mode)

        # 4. 如果系统级策略修改了 input，保留工具级的 updated_input
        if system_decision.behavior == PermissionBehavior.ALLOW:
            # 系统级 allow，使用工具级的 updated_input（如果有）
            return PermissionDecision.allow(
                updated_input=tool_decision.updated_input
            )

        # 系统级 deny/ask，直接返回
        return system_decision
