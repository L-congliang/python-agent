"""CLI 事件流测试

验证 create_message_handler() 的事件编排与 flush 行为。
注意：这些测试主要验证消息处理器的内部逻辑，不经过真实的 AgentApp 消费链路。
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from agent.core.model import MimoClient
from agent.core.loop import AgentLoop, LoopConfig
from agent.core.types import (
    StreamEvent, ToolCall, ToolResult, ObservationMetadata,
    PermissionConfirmationOutcome, PermissionRequest,
)
from agent.tools.registry import ToolRegistry, register_base_tools
from agent.main import create_message_handler, create_agent_loop


# ============================================================
# 辅助函数
# ============================================================


def _always_approve_handler(request: PermissionRequest) -> PermissionConfirmationOutcome:
    """总是批准的权限处理器"""
    return PermissionConfirmationOutcome.APPROVED


def create_test_handler(
    artifact_dir: str | None = None,
) -> tuple[callable, AgentLoop]:
    """创建测试用的消息处理器，返回 (handler, loop)"""
    mock_client = MagicMock()

    config = LoopConfig(
        model="test",
        artifact_dir=artifact_dir,
    )
    config.permission_handler = _always_approve_handler

    registry = register_base_tools(ToolRegistry())
    loop = AgentLoop(mock_client, registry, config=config)
    handler = create_message_handler(loop)

    return handler, loop


# ============================================================
# 事件流测试
# ============================================================


class TestCLIEventFlow:
    """CLI 事件流测试。"""

    def test_handler_yields_text_events(self) -> None:
        """handler 应该 yield text 事件"""
        handler, loop = create_test_handler()

        # Mock run_stream 返回文本 chunk
        with patch.object(loop, 'run_stream', return_value=iter(["hello", "world"])):
            events = list(handler("test"))

        # 验证事件
        text_events = [e for e in events if e.type == "text"]
        assert len(text_events) == 2
        assert text_events[0].content == "hello"
        assert text_events[1].content == "world"

    def test_handler_yields_tool_result_events(self) -> None:
        """handler 应该 yield tool_result 事件"""
        handler, loop = create_test_handler()

        # Mock run_stream，触发 on_tool_result 回调
        def mock_run_stream(msg):
            # 模拟工具执行
            tool_call = ToolCall(id="test", name="bash", arguments={})
            result = ToolResult(
                output="tool output",
                observation=ObservationMetadata(preview="preview"),
            )
            if loop._config.on_tool_result:
                loop._config.on_tool_result(tool_call, result)
            yield "text chunk"

        with patch.object(loop, 'run_stream', side_effect=mock_run_stream):
            events = list(handler("test"))

        # 验证事件
        tool_events = [e for e in events if e.type == "tool_result"]
        assert len(tool_events) == 1
        assert tool_events[0].content == "tool output"
        assert tool_events[0].observation is not None

    def test_handler_flushes_remaining_events(self) -> None:
        """handler 应该在流结束后 flush 剩余事件"""
        handler, loop = create_test_handler()

        # Mock run_stream，在结束后触发回调
        def mock_run_stream(msg):
            yield "text chunk"
            # 流结束后触发回调
            tool_call = ToolCall(id="test", name="bash", arguments={})
            result = ToolResult(output="final output")
            if loop._config.on_tool_result:
                loop._config.on_tool_result(tool_call, result)

        with patch.object(loop, 'run_stream', side_effect=mock_run_stream):
            events = list(handler("test"))

        # 验证事件
        tool_events = [e for e in events if e.type == "tool_result"]
        assert len(tool_events) == 1
        assert tool_events[0].content == "final output"

    def test_handler_preserves_observation(self) -> None:
        """handler 应该保留 observation"""
        handler, loop = create_test_handler()

        # Mock run_stream
        def mock_run_stream(msg):
            tool_call = ToolCall(id="test", name="bash", arguments={})
            result = ToolResult(
                output="full output",
                observation=ObservationMetadata(
                    preview="preview",
                    was_truncated=True,
                    artifact_path="/tmp/test.txt",
                ),
            )
            if loop._config.on_tool_result:
                loop._config.on_tool_result(tool_call, result)
            yield "text"

        with patch.object(loop, 'run_stream', side_effect=mock_run_stream):
            events = list(handler("test"))

        # 验证 observation 被保留
        tool_events = [e for e in events if e.type == "tool_result"]
        assert len(tool_events) == 1
        assert tool_events[0].observation is not None
        assert tool_events[0].observation.artifact_path == "/tmp/test.txt"

    def test_handler_clears_events_between_calls(self) -> None:
        """handler 应该在每次调用时清空事件队列"""
        handler, loop = create_test_handler()

        # 第一次调用
        def mock_run_stream_1(msg):
            tool_call = ToolCall(id="test1", name="bash", arguments={})
            result = ToolResult(output="output1")
            if loop._config.on_tool_result:
                loop._config.on_tool_result(tool_call, result)
            yield "text1"

        with patch.object(loop, 'run_stream', side_effect=mock_run_stream_1):
            events1 = list(handler("test1"))

        # 第二次调用
        def mock_run_stream_2(msg):
            yield "text2"

        with patch.object(loop, 'run_stream', side_effect=mock_run_stream_2):
            events2 = list(handler("test2"))

        # 验证第二次调用没有第一次的事件
        tool_events_2 = [e for e in events2 if e.type == "tool_result"]
        assert len(tool_events_2) == 0


# ============================================================
# 边界测试
# ============================================================


class TestCLIEventFlowEdgeCases:
    """边界情况测试。"""

    def test_no_tool_calls(self) -> None:
        """没有工具调用时，只 yield text 事件"""
        handler, loop = create_test_handler()

        with patch.object(loop, 'run_stream', return_value=iter(["hello"])):
            events = list(handler("test"))

        assert all(e.type == "text" for e in events)

    def test_multiple_tool_calls(self) -> None:
        """多次工具调用"""
        handler, loop = create_test_handler()

        def mock_run_stream(msg):
            for i in range(3):
                tool_call = ToolCall(id=f"test{i}", name="bash", arguments={})
                result = ToolResult(output=f"output{i}")
                if loop._config.on_tool_result:
                    loop._config.on_tool_result(tool_call, result)
                yield f"text{i}"

        with patch.object(loop, 'run_stream', side_effect=mock_run_stream):
            events = list(handler("test"))

        # 验证事件顺序
        text_events = [e for e in events if e.type == "text"]
        tool_events = [e for e in events if e.type == "tool_result"]
        assert len(text_events) == 3
        assert len(tool_events) == 3

    def test_error_result(self) -> None:
        """错误结果也应该被 yield"""
        handler, loop = create_test_handler()

        def mock_run_stream(msg):
            tool_call = ToolCall(id="test", name="bash", arguments={})
            result = ToolResult(output="error message", is_error=True)
            if loop._config.on_tool_result:
                loop._config.on_tool_result(tool_call, result)
            yield "text"

        with patch.object(loop, 'run_stream', side_effect=mock_run_stream):
            events = list(handler("test"))

        tool_events = [e for e in events if e.type == "tool_result"]
        assert len(tool_events) == 1
        assert tool_events[0].is_error is True


# ============================================================
# 默认入口集成测试
# ============================================================


class TestDefaultEntryPoint:
    """默认入口集成测试。"""

    def test_create_message_handler_returns_callable(self) -> None:
        """create_message_handler 返回可调用对象"""
        handler, loop = create_test_handler()
        assert callable(handler)

    def test_handler_accepts_string(self) -> None:
        """handler 接受字符串输入"""
        handler, loop = create_test_handler()

        with patch.object(loop, 'run_stream', return_value=iter(["hello"])):
            events = list(handler("test input"))

        assert len(events) > 0
