"""F09 权限检查器测试

测试 PermissionChecker 和 check_system_policy 的行为。
覆盖：权限模式、系统级策略、工具级决策合并。
"""

from unittest.mock import MagicMock

import pytest

from agent.core.types import (
    PermissionBehavior,
    PermissionDecision,
    ToolResult,
)
from agent.tools.base import Tool, build_tool
from agent.core.context import ToolUseContext
from agent.permissions.checker import (
    PermissionMode,
    PermissionChecker,
    check_system_policy,
)


# ============================================================
# 辅助函数
# ============================================================

def _make_tool(
    name: str = "test_tool",
    is_read_only: bool = False,
    is_destructive: bool = False,
    check_permissions: object = None,
) -> Tool:
    """创建测试用工具。"""
    kwargs: dict = {
        "name": name,
        "description": "Test tool",
        "parameters": {"type": "object", "properties": {}},
        "execute_fn": lambda input, ctx: ToolResult(output="ok"),
        "is_read_only": lambda input: is_read_only,
        "is_destructive": lambda input: is_destructive,
    }
    if check_permissions is not None:
        kwargs["check_permissions"] = check_permissions
    return build_tool(**kwargs)


def _make_context() -> ToolUseContext:
    """创建测试用上下文。"""
    return ToolUseContext(model="test-model")


# ============================================================
# PermissionMode 测试
# ============================================================

class TestPermissionMode:
    """PermissionMode 枚举测试。"""

    def test_default_value(self) -> None:
        """默认模式是 DEFAULT。"""
        assert PermissionMode.DEFAULT.value == "default"

    def test_plan_value(self) -> None:
        """计划模式是 PLAN。"""
        assert PermissionMode.PLAN.value == "plan"

    def test_member_count(self) -> None:
        """只有两个模式。"""
        assert len(PermissionMode) == 2


# ============================================================
# check_system_policy 测试
# ============================================================

class TestCheckSystemPolicy:
    """check_system_policy 函数测试。"""

    def test_default_mode_read_only_tool(self) -> None:
        """default 模式 + 只读工具 → allow。"""
        tool = _make_tool(is_read_only=True)
        decision = check_system_policy(tool, {}, PermissionMode.DEFAULT)
        assert decision.behavior == PermissionBehavior.ALLOW

    def test_default_mode_non_read_only_tool(self) -> None:
        """default 模式 + 非只读工具 → ask。"""
        tool = _make_tool(is_read_only=False)
        decision = check_system_policy(tool, {}, PermissionMode.DEFAULT)
        assert decision.behavior == PermissionBehavior.ASK
        assert "确认" in decision.message

    def test_default_mode_destructive_tool(self) -> None:
        """default 模式 + 破坏性工具 → ask。"""
        tool = _make_tool(is_read_only=False, is_destructive=True)
        decision = check_system_policy(tool, {}, PermissionMode.DEFAULT)
        assert decision.behavior == PermissionBehavior.ASK

    def test_plan_mode_read_only_tool(self) -> None:
        """plan 模式 + 只读工具 → allow。"""
        tool = _make_tool(is_read_only=True)
        decision = check_system_policy(tool, {}, PermissionMode.PLAN)
        assert decision.behavior == PermissionBehavior.ALLOW

    def test_plan_mode_non_read_only_tool(self) -> None:
        """plan 模式 + 非只读工具 → deny。"""
        tool = _make_tool(is_read_only=False)
        decision = check_system_policy(tool, {}, PermissionMode.PLAN)
        assert decision.behavior == PermissionBehavior.DENY
        assert "计划模式" in decision.message

    def test_plan_mode_destructive_tool(self) -> None:
        """plan 模式 + 破坏性工具 → deny。"""
        tool = _make_tool(is_read_only=False, is_destructive=True)
        decision = check_system_policy(tool, {}, PermissionMode.PLAN)
        assert decision.behavior == PermissionBehavior.DENY

    def test_ask_message_contains_tool_name(self) -> None:
        """ask 消息包含工具名。"""
        tool = _make_tool(name="bash", is_read_only=False)
        decision = check_system_policy(tool, {}, PermissionMode.DEFAULT)
        assert "bash" in decision.message

    def test_deny_message_contains_tool_name(self) -> None:
        """deny 消息包含工具名。"""
        tool = _make_tool(name="write", is_read_only=False)
        decision = check_system_policy(tool, {}, PermissionMode.PLAN)
        assert "write" in decision.message


# ============================================================
# PermissionChecker 测试
# ============================================================

class TestPermissionChecker:
    """PermissionChecker 类测试。"""

    def test_default_mode(self) -> None:
        """默认模式是 DEFAULT。"""
        checker = PermissionChecker()
        assert checker.mode == PermissionMode.DEFAULT

    def test_custom_mode(self) -> None:
        """可以指定初始模式。"""
        checker = PermissionChecker(mode=PermissionMode.PLAN)
        assert checker.mode == PermissionMode.PLAN

    def test_set_mode(self) -> None:
        """可以切换模式。"""
        checker = PermissionChecker()
        checker.set_mode(PermissionMode.PLAN)
        assert checker.mode == PermissionMode.PLAN

    def test_check_read_only_in_default(self) -> None:
        """default 模式 + 只读工具 → allow。"""
        checker = PermissionChecker()
        tool = _make_tool(is_read_only=True)
        ctx = _make_context()
        decision = checker.check(tool, {}, ctx)
        assert decision.behavior == PermissionBehavior.ALLOW

    def test_check_non_read_only_in_default(self) -> None:
        """default 模式 + 非只读工具 → ask。"""
        checker = PermissionChecker()
        tool = _make_tool(is_read_only=False)
        ctx = _make_context()
        decision = checker.check(tool, {}, ctx)
        assert decision.behavior == PermissionBehavior.ASK

    def test_check_read_only_in_plan(self) -> None:
        """plan 模式 + 只读工具 → allow。"""
        checker = PermissionChecker(mode=PermissionMode.PLAN)
        tool = _make_tool(is_read_only=True)
        ctx = _make_context()
        decision = checker.check(tool, {}, ctx)
        assert decision.behavior == PermissionBehavior.ALLOW

    def test_check_non_read_only_in_plan(self) -> None:
        """plan 模式 + 非只读工具 → deny。"""
        checker = PermissionChecker(mode=PermissionMode.PLAN)
        tool = _make_tool(is_read_only=False)
        ctx = _make_context()
        decision = checker.check(tool, {}, ctx)
        assert decision.behavior == PermissionBehavior.DENY


# ============================================================
# 工具级决策合并测试
# ============================================================

class TestToolLevelOverride:
    """工具级决策优先级测试。"""

    def test_tool_deny_overrides_system_allow(self) -> None:
        """工具级 deny 覆盖系统级 allow。"""
        def tool_check(input: dict, ctx: ToolUseContext) -> PermissionDecision:
            return PermissionDecision.deny("工具拒绝")

        tool = _make_tool(is_read_only=True, check_permissions=tool_check)
        checker = PermissionChecker()
        ctx = _make_context()
        decision = checker.check(tool, {}, ctx)
        assert decision.behavior == PermissionBehavior.DENY
        assert decision.message == "工具拒绝"

    def test_tool_ask_overrides_system_allow(self) -> None:
        """工具级 ask 覆盖系统级 allow。"""
        def tool_check(input: dict, ctx: ToolUseContext) -> PermissionDecision:
            return PermissionDecision.ask("请确认")

        tool = _make_tool(is_read_only=True, check_permissions=tool_check)
        checker = PermissionChecker()
        ctx = _make_context()
        decision = checker.check(tool, {}, ctx)
        assert decision.behavior == PermissionBehavior.ASK
        assert decision.message == "请确认"

    def test_tool_allow_system_ask(self) -> None:
        """工具级 allow + 系统级 ask → ask。"""
        def tool_check(input: dict, ctx: ToolUseContext) -> PermissionDecision:
            return PermissionDecision.allow()

        tool = _make_tool(is_read_only=False, check_permissions=tool_check)
        checker = PermissionChecker()
        ctx = _make_context()
        decision = checker.check(tool, {}, ctx)
        assert decision.behavior == PermissionBehavior.ASK

    def test_tool_allow_system_deny(self) -> None:
        """工具级 allow + 系统级 deny → deny。"""
        def tool_check(input: dict, ctx: ToolUseContext) -> PermissionDecision:
            return PermissionDecision.allow()

        tool = _make_tool(is_read_only=False, check_permissions=tool_check)
        checker = PermissionChecker(mode=PermissionMode.PLAN)
        ctx = _make_context()
        decision = checker.check(tool, {}, ctx)
        assert decision.behavior == PermissionBehavior.DENY

    def test_tool_updated_input_preserved(self) -> None:
        """工具级 updated_input 正确传递。"""
        modified_input = {"command": "ls -la"}

        def tool_check(input: dict, ctx: ToolUseContext) -> PermissionDecision:
            return PermissionDecision.allow(updated_input=modified_input)

        tool = _make_tool(is_read_only=True, check_permissions=tool_check)
        checker = PermissionChecker()
        ctx = _make_context()
        decision = checker.check(tool, {"command": "ls"}, ctx)
        assert decision.behavior == PermissionBehavior.ALLOW
        assert decision.updated_input == modified_input

    def test_tool_deny_in_plan_mode(self) -> None:
        """plan 模式下工具级 deny 优先。"""
        def tool_check(input: dict, ctx: ToolUseContext) -> PermissionDecision:
            return PermissionDecision.deny("自定义拒绝")

        tool = _make_tool(is_read_only=True, check_permissions=tool_check)
        checker = PermissionChecker(mode=PermissionMode.PLAN)
        ctx = _make_context()
        decision = checker.check(tool, {}, ctx)
        assert decision.behavior == PermissionBehavior.DENY
        assert decision.message == "自定义拒绝"


# ============================================================
# 边界情况测试
# ============================================================

class TestEdgeCases:
    """边界情况测试。"""

    def test_mode_switch_affects_subsequent_checks(self) -> None:
        """切换模式后检查结果变化。"""
        checker = PermissionChecker()
        tool = _make_tool(is_read_only=False)
        ctx = _make_context()

        # default 模式 → ask
        decision = checker.check(tool, {}, ctx)
        assert decision.behavior == PermissionBehavior.ASK

        # 切换到 plan 模式 → deny
        checker.set_mode(PermissionMode.PLAN)
        decision = checker.check(tool, {}, ctx)
        assert decision.behavior == PermissionBehavior.DENY

    def test_multiple_checks_same_tool(self) -> None:
        """同一工具多次检查结果一致。"""
        checker = PermissionChecker()
        tool = _make_tool(is_read_only=True)
        ctx = _make_context()

        for _ in range(5):
            decision = checker.check(tool, {}, ctx)
            assert decision.behavior == PermissionBehavior.ALLOW

    def test_different_tools_different_results(self) -> None:
        """不同工具在同一模式下结果不同。"""
        checker = PermissionChecker()
        ctx = _make_context()

        read_tool = _make_tool(name="read", is_read_only=True)
        write_tool = _make_tool(name="write", is_read_only=False)

        read_decision = checker.check(read_tool, {}, ctx)
        write_decision = checker.check(write_tool, {}, ctx)

        assert read_decision.behavior == PermissionBehavior.ALLOW
        assert write_decision.behavior == PermissionBehavior.ASK
