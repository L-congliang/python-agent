"""Loop 侧 Observation Reinjection 测试

验证 _handle_tool_results 和 _resolve_observation_content 的新行为。
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from agent.core.types import ToolResult, ObservationMetadata, ToolCall, Role, Message
from agent.core.loop import AgentLoop


# ============================================================
# 辅助函数
# ============================================================


def make_tool_call(tool_call_id: str = "test_id", name: str = "bash") -> ToolCall:
    """创建测试用的 ToolCall"""
    return ToolCall(id=tool_call_id, name=name, arguments={})


def make_result(
    output: str,
    observation: ObservationMetadata | None = None,
    is_error: bool = False,
) -> ToolResult:
    """创建测试用的 ToolResult"""
    return ToolResult(output=output, is_error=is_error, observation=observation)


def create_test_loop() -> AgentLoop:
    """创建测试用的 AgentLoop 实例"""
    mock_client = MagicMock()
    mock_adapter = MagicMock()
    mock_registry = MagicMock()
    return AgentLoop(client=mock_client, registry=mock_registry, adapter=mock_adapter)


# ============================================================
# _resolve_observation_content 测试
# ============================================================


class TestResolveObservationContent:
    """_resolve_observation_content 单元测试。"""

    def setup_method(self) -> None:
        """创建 AgentLoop 实例"""
        self.loop = create_test_loop()

    def test_backward_compatible_no_observation(self) -> None:
        """向后兼容：没有 observation 时使用 output"""
        result = make_result("original output")
        content = self.loop._resolve_observation_content(result)
        assert content == "original output"

    def test_backward_compatible_observation_none(self) -> None:
        """向后兼容：observation 为 None 时使用 output"""
        result = make_result("original output", observation=None)
        content = self.loop._resolve_observation_content(result)
        assert content == "original output"

    def test_observation_with_preview_only(self) -> None:
        """有 preview 但无 artifact_path"""
        obs = ObservationMetadata(preview="preview content")
        result = make_result("full output", observation=obs)
        content = self.loop._resolve_observation_content(result)
        assert content == "preview content"

    def test_observation_with_preview_and_artifact(self) -> None:
        """有 preview 且有 artifact_path"""
        obs = ObservationMetadata(
            preview="first 100 chars...",
            artifact_path="/tmp/artifacts/bash_output.txt",
        )
        result = make_result("full output here...", observation=obs)
        content = self.loop._resolve_observation_content(result)

        assert "first 100 chars..." in content
        assert "[完整输出已保存到: /tmp/artifacts/bash_output.txt]" in content

    def test_observation_with_empty_preview(self) -> None:
        """preview 为空字符串"""
        obs = ObservationMetadata(preview="")
        result = make_result("full output", observation=obs)
        content = self.loop._resolve_observation_content(result)
        assert content == ""

    def test_observation_truncated_flag(self) -> None:
        """观察 truncated 标记"""
        obs = ObservationMetadata(
            preview="truncated...",
            was_truncated=True,
            full_output_chars=5000,
        )
        result = make_result("full output", observation=obs)
        content = self.loop._resolve_observation_content(result)
        assert "truncated..." in content

    def test_error_result_with_observation(self) -> None:
        """错误结果也支持 observation"""
        obs = ObservationMetadata(preview="error preview")
        result = make_result("full error", is_error=True, observation=obs)
        content = self.loop._resolve_observation_content(result)
        assert content == "error preview"

    def test_non_string_output_backward_compatible(self) -> None:
        """非字符串 output 的向后兼容"""
        result = make_result("12345")  # output 是字符串
        content = self.loop._resolve_observation_content(result)
        assert content == "12345"


# ============================================================
# _handle_tool_results 集成测试
# ============================================================


class TestHandleToolResults:
    """_handle_tool_results 集成测试。"""

    def setup_method(self) -> None:
        """创建 AgentLoop 实例"""
        self.loop = create_test_loop()

    def test_backward_compatible_single_result(self) -> None:
        """向后兼容：单个工具结果"""
        tool_call = make_tool_call("call_1")
        result = make_result("tool output")

        self.loop._handle_tool_results([tool_call], [result])

        # 验证消息被添加
        assert len(self.loop._messages) == 1
        msg = self.loop._messages[0]
        assert msg["role"] == "user"
        assert len(msg["content"]) == 1
        assert msg["content"][0]["content"] == "tool output"

    def test_observation_preview_injected(self) -> None:
        """observation preview 被注入到消息历史"""
        tool_call = make_tool_call("call_1")
        obs = ObservationMetadata(preview="preview text")
        result = make_result("full output", observation=obs)

        self.loop._handle_tool_results([tool_call], [result])

        msg = self.loop._messages[0]
        assert msg["content"][0]["content"] == "preview text"

    def test_observation_with_artifact_hint(self) -> None:
        """artifact 路径提示被附加到 preview"""
        tool_call = make_tool_call("call_1")
        obs = ObservationMetadata(
            preview="preview",
            artifact_path="/tmp/output.txt",
        )
        result = make_result("full output", observation=obs)

        self.loop._handle_tool_results([tool_call], [result])

        content = self.loop._messages[0]["content"][0]["content"]
        assert "preview" in content
        assert "[完整输出已保存到: /tmp/output.txt]" in content

    def test_multiple_results_mixed(self) -> None:
        """混合：有 observation 和没有 observation 的结果"""
        call_1 = make_tool_call("call_1")
        call_2 = make_tool_call("call_2")

        result_1 = make_result("old style output")  # 没有 observation
        obs_2 = ObservationMetadata(preview="new style preview")
        result_2 = make_result("new style output", observation=obs_2)

        self.loop._handle_tool_results([call_1, call_2], [result_1, result_2])

        msg = self.loop._messages[0]
        assert len(msg["content"]) == 2
        assert msg["content"][0]["content"] == "old style output"
        assert msg["content"][1]["content"] == "new style preview"

    def test_error_result_preserved(self) -> None:
        """错误结果的 is_error 标记被保留"""
        tool_call = make_tool_call("call_1")
        obs = ObservationMetadata(preview="error preview")
        result = make_result("full error", is_error=True, observation=obs)

        self.loop._handle_tool_results([tool_call], [result])

        msg = self.loop._messages[0]
        assert msg["content"][0]["is_error"] is True


# ============================================================
# 边界测试
# ============================================================


class TestObservationEdgeCases:
    """边界情况测试。"""

    def setup_method(self) -> None:
        """创建 AgentLoop 实例"""
        self.loop = create_test_loop()

    def test_unicode_content(self) -> None:
        """Unicode 内容正常处理"""
        obs = ObservationMetadata(preview="中文预览...")
        result = make_result("中文完整输出", observation=obs)

        content = self.loop._resolve_observation_content(result)
        assert content == "中文预览..."

    def test_large_preview(self) -> None:
        """大 preview 正常处理"""
        large_preview = "x" * 10000
        obs = ObservationMetadata(preview=large_preview)
        result = make_result("full output", observation=obs)

        content = self.loop._resolve_observation_content(result)
        assert len(content) == 10000

    def test_observation_preview_none(self) -> None:
        """observation 存在但 preview 为 None"""
        obs = ObservationMetadata(preview=None, was_truncated=True)
        result = make_result("fallback output", observation=obs)

        # preview 为 None 时应回退到 output
        content = self.loop._resolve_observation_content(result)
        assert content == "fallback output"
