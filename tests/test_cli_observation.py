"""CLI Observation 可见性测试

验证 CLI 的 show_tool_result 方法支持 observation 信息。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.core.types import ObservationMetadata, StreamEvent
from agent.cli.app import AgentApp


# ============================================================
# 辅助函数
# ============================================================


def create_test_app() -> AgentApp:
    """创建测试用的 AgentApp"""
    mock_on_message = MagicMock()
    return AgentApp(on_message=mock_on_message)


# ============================================================
# show_tool_result 测试
# ============================================================


class TestShowToolResult:
    """show_tool_result 方法测试。"""

    def test_basic_output(self) -> None:
        """基本输出"""
        app = create_test_app()
        # 不应该抛出异常
        app.show_tool_result("test output", is_error=False)

    def test_error_output(self) -> None:
        """错误输出"""
        app = create_test_app()
        app.show_tool_result("error message", is_error=True)

    def test_with_observation_truncated(self) -> None:
        """带 observation 的截断输出"""
        app = create_test_app()
        obs = ObservationMetadata(
            preview="preview text",
            was_truncated=True,
            full_output_chars=1000,
            artifact_path="/tmp/test.txt",
        )
        app.show_tool_result("full output", is_error=False, observation=obs)

    def test_with_observation_not_truncated(self) -> None:
        """带 observation 但未截断"""
        app = create_test_app()
        obs = ObservationMetadata(
            preview="full output",
            was_truncated=False,
            full_output_chars=10,
        )
        app.show_tool_result("full output", is_error=False, observation=obs)

    def test_without_observation(self) -> None:
        """不带 observation（向后兼容）"""
        app = create_test_app()
        app.show_tool_result("test output", is_error=False, observation=None)

    def test_observation_with_artifact(self) -> None:
        """observation 带 artifact 路径"""
        app = create_test_app()
        obs = ObservationMetadata(
            preview="preview",
            was_truncated=True,
            full_output_chars=5000,
            artifact_path="/tmp/artifacts/bash_123.txt",
        )
        app.show_tool_result("full output", is_error=False, observation=obs)

    def test_observation_without_artifact(self) -> None:
        """observation 不带 artifact 路径"""
        app = create_test_app()
        obs = ObservationMetadata(
            preview="preview",
            was_truncated=True,
            full_output_chars=5000,
            artifact_path=None,
        )
        app.show_tool_result("full output", is_error=False, observation=obs)


# ============================================================
# _handle_event 测试
# ============================================================


class TestHandleEvent:
    """_handle_event 方法测试。"""

    def test_text_event(self) -> None:
        """text 事件"""
        app = create_test_app()
        event = StreamEvent(type="text", content="hello")
        app._handle_event(event)

    def test_tool_result_event_without_observation(self) -> None:
        """tool_result 事件（无 observation）"""
        app = create_test_app()
        event = StreamEvent(type="tool_result", content="result", is_error=False)
        app._handle_event(event)

    def test_tool_result_event_with_observation(self) -> None:
        """tool_result 事件（有 observation）"""
        app = create_test_app()
        obs = ObservationMetadata(
            preview="preview",
            was_truncated=True,
            full_output_chars=1000,
        )
        event = StreamEvent(
            type="tool_result",
            content="full result",
            is_error=False,
            observation=obs,
        )
        app._handle_event(event)


# ============================================================
# 边界测试
# ============================================================


class TestCLIObservationEdgeCases:
    """边界情况测试。"""

    def test_unicode_content(self) -> None:
        """Unicode 内容"""
        app = create_test_app()
        obs = ObservationMetadata(
            preview="中文预览...",
            was_truncated=True,
            full_output_chars=100,
        )
        app.show_tool_result("中文完整输出", is_error=False, observation=obs)

    def test_large_output(self) -> None:
        """大输出"""
        app = create_test_app()
        large_output = "x" * 10000
        obs = ObservationMetadata(
            preview=large_output[:100],
            was_truncated=True,
            full_output_chars=10000,
        )
        app.show_tool_result(large_output, is_error=False, observation=obs)

    def test_empty_output(self) -> None:
        """空输出"""
        app = create_test_app()
        app.show_tool_result("", is_error=False, observation=None)
