"""Plan Mode 测试

测试覆盖：
- Plan Mode 激活（关键词检测）
- Plan Mode 权限控制（写操作被拦截）
- Plan Mode 确认/取消
"""

import pytest

from agent.core.loop import AgentLoop, LoopConfig
from agent.core.model import MimoClient
from agent.core.model import StreamResult
from agent.tools.registry import ToolRegistry
from agent.tools.base import build_tool
from agent.core.types import ToolResult, PermissionDecision
from agent.core.context import ToolUseContext
from agent.permissions.checker import PermissionChecker, PermissionMode


# ========== 意图检测测试 ==========


class TestPlanningIntentDetection:
    """规划意图检测测试"""

    def _make_loop(self) -> AgentLoop:
        """创建测试用的 AgentLoop"""
        registry = ToolRegistry()
        config = LoopConfig(enable_trace=False, enable_checkpoint=False)
        # 使用一个简单的 fake client
        class FakeClient:
            def chat_stream(self, messages, system=""):
                raise NotImplementedError("Should not be called")

        loop = AgentLoop(FakeClient(), registry, config=config)  # type: ignore[arg-type]
        return loop

    def test_detect_planning_intent_chinese(self):
        """检测中文规划意图"""
        loop = self._make_loop()
        assert loop._detect_planning_intent("先规划一下怎么做")
        assert loop._detect_planning_intent("列出计划")
        assert loop._detect_planning_intent("做个计划")
        assert loop._detect_planning_intent("规划一下")

    def test_no_planning_intent(self):
        """普通输入不触发规划"""
        loop = self._make_loop()
        assert not loop._detect_planning_intent("读取 main.py")
        assert not loop._detect_planning_intent("帮我改个 bug")

    def test_detect_confirmation_intent(self):
        """检测确认意图"""
        loop = self._make_loop()
        assert loop._detect_confirmation_intent("确认")
        assert loop._detect_confirmation_intent("执行")
        assert loop._detect_confirmation_intent("开始")
        assert loop._detect_confirmation_intent("好的")

    def test_detect_cancel_intent(self):
        """检测取消意图"""
        loop = self._make_loop()
        assert loop._detect_cancel_intent("取消")
        assert loop._detect_cancel_intent("直接改吧")


# ========== 权限控制测试 ==========


class TestPlanModePermission:
    """Plan Mode 权限控制测试"""

    def test_plan_mode_denies_write(self):
        """Plan Mode 下写操作被拒绝"""
        checker = PermissionChecker(mode=PermissionMode.PLAN)
        write_tool = build_tool(
            name="write",
            description="写入文件",
            parameters={},
            execute_fn=lambda input, ctx: ToolResult(output="ok"),
            is_read_only=lambda input: False,
        )
        context = ToolUseContext(
            model="test",
            tools=[],
            abort_controller=None,  # type: ignore[arg-type]
            file_read_state=None,  # type: ignore[arg-type]
            messages=[],
        )
        decision = checker.check(write_tool, {}, context)
        assert decision.behavior.value == "deny"

    def test_plan_mode_allows_read(self):
        """Plan Mode 下读操作被允许"""
        checker = PermissionChecker(mode=PermissionMode.PLAN)
        read_tool = build_tool(
            name="read",
            description="读取文件",
            parameters={},
            execute_fn=lambda input, ctx: ToolResult(output="ok"),
            is_read_only=lambda input: True,
        )
        context = ToolUseContext(
            model="test",
            tools=[],
            abort_controller=None,  # type: ignore[arg-type]
            file_read_state=None,  # type: ignore[arg-type]
            messages=[],
        )
        decision = checker.check(read_tool, {}, context)
        assert decision.behavior.value == "allow"

    def test_default_mode_allows_write(self):
        """Default 模式下写操作需要确认"""
        checker = PermissionChecker(mode=PermissionMode.DEFAULT)
        write_tool = build_tool(
            name="write",
            description="写入文件",
            parameters={},
            execute_fn=lambda input, ctx: ToolResult(output="ok"),
            is_read_only=lambda input: False,
        )
        context = ToolUseContext(
            model="test",
            tools=[],
            abort_controller=None,  # type: ignore[arg-type]
            file_read_state=None,  # type: ignore[arg-type]
            messages=[],
        )
        decision = checker.check(write_tool, {}, context)
        assert decision.behavior.value == "ask"

    def test_default_mode_ask_is_not_allow(self):
        """Default 模式下 ASK 不能被当成 ALLOW"""
        checker = PermissionChecker(mode=PermissionMode.DEFAULT)
        write_tool = build_tool(
            name="write",
            description="写入文件",
            parameters={},
            execute_fn=lambda input, ctx: ToolResult(output="ok"),
            is_read_only=lambda input: False,
        )
        context = ToolUseContext(
            model="test",
            tools=[],
            abort_controller=None,  # type: ignore[arg-type]
            file_read_state=None,  # type: ignore[arg-type]
            messages=[],
        )
        decision = checker.check(write_tool, {}, context)
        assert decision.behavior.value == "ask"


# ========== LoopConfig 测试 ==========


class TestPlanModeConfig:
    """Plan Mode 配置测试"""

    def test_plan_mode_default_off(self):
        """Plan Mode 默认关闭"""
        config = LoopConfig()
        assert config.plan_mode is False

    def test_plan_mode_can_be_enabled(self):
        """Plan Mode 可以启用"""
        config = LoopConfig(plan_mode=True)
        assert config.plan_mode is True


class TestPlanModeStreamParity:
    """run_stream 与 run 的 Plan Mode 行为一致性测试"""

    @staticmethod
    def _text_stream(text: str) -> StreamResult:
        return StreamResult(
            text=iter([text]),
            content_blocks=[{"type": "text", "text": text}],
        )

    def _make_loop(self, responses, *, plan_mode: bool = False) -> AgentLoop:
        class FakeClient:
            def __init__(self, stream_responses):
                self._responses = iter(stream_responses)

            def chat_stream(self, messages, system="", tools=None):
                return next(self._responses)

        registry = ToolRegistry()
        config = LoopConfig(
            plan_mode=plan_mode,
            enable_trace=False,
            enable_checkpoint=False,
        )
        return AgentLoop(FakeClient(responses), registry, config=config)  # type: ignore[arg-type]

    def test_run_stream_enables_plan_mode(self):
        loop = self._make_loop([self._text_stream("先做计划")])

        list(loop.run_stream("先规划一下怎么做"))

        assert loop._config.plan_mode is True

    def test_run_stream_disables_plan_mode_on_confirmation(self):
        loop = self._make_loop([self._text_stream("开始执行")], plan_mode=True)

        list(loop.run_stream("确认执行"))

        assert loop._config.plan_mode is False
