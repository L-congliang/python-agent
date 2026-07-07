"""Observation Budget 契约测试

验证 ToolResult 的 observation 字段和 ObservationMetadata 结构。
"""

from __future__ import annotations

import pytest

from agent.core.types import ToolResult, ObservationMetadata


# ============================================================
# ObservationMetadata 测试
# ============================================================


class TestObservationMetadata:
    """ObservationMetadata 数据类测试。"""

    def test_default_values(self) -> None:
        """默认值：所有字段都有合理的默认值"""
        obs = ObservationMetadata()
        assert obs.preview is None
        assert obs.artifact_path is None
        assert obs.was_truncated is False
        assert obs.full_output_chars == 0

    def test_with_preview_only(self) -> None:
        """只有 preview 的情况（短输出，未截断）"""
        obs = ObservationMetadata(preview="short output")
        assert obs.preview == "short output"
        assert obs.artifact_path is None
        assert obs.was_truncated is False
        assert obs.full_output_chars == 0

    def test_with_full_metadata(self) -> None:
        """完整的 metadata（长输出，已截断）"""
        obs = ObservationMetadata(
            preview="first 100 chars...",
            artifact_path="/tmp/artifacts/run_123/bash_output.txt",
            was_truncated=True,
            full_output_chars=5000,
        )
        assert obs.preview == "first 100 chars..."
        assert obs.artifact_path == "/tmp/artifacts/run_123/bash_output.txt"
        assert obs.was_truncated is True
        assert obs.full_output_chars == 5000

    def test_truncated_without_artifact(self) -> None:
        """截断但没有保存 artifact 的情况"""
        obs = ObservationMetadata(
            preview="truncated...",
            was_truncated=True,
            full_output_chars=1000,
        )
        assert obs.was_truncated is True
        assert obs.artifact_path is None


# ============================================================
# ToolResult + ObservationMetadata 集成测试
# ============================================================


class TestToolResultObservation:
    """ToolResult 的 observation 字段测试。"""

    def test_backward_compatible(self) -> None:
        """向后兼容：旧用法不传 observation"""
        result = ToolResult(output="some output")
        assert result.output == "some output"
        assert result.is_error is False
        assert result.new_messages is None
        assert result.observation is None

    def test_with_observation(self) -> None:
        """新用法：带 observation"""
        obs = ObservationMetadata(
            preview="first 50 chars...",
            was_truncated=True,
            full_output_chars=500,
        )
        result = ToolResult(
            output="full output here...",
            observation=obs,
        )
        assert result.output == "full output here..."
        assert result.observation is not None
        assert result.observation.preview == "first 50 chars..."
        assert result.observation.was_truncated is True

    def test_error_with_observation(self) -> None:
        """错误结果也可以带 observation"""
        obs = ObservationMetadata(
            preview="error preview",
            was_truncated=False,
        )
        result = ToolResult(
            output="full error message",
            is_error=True,
            observation=obs,
        )
        assert result.is_error is True
        assert result.observation.preview == "error preview"

    def test_observation_none_access(self) -> None:
        """observation 为 None 时，访问属性应抛 AttributeError"""
        result = ToolResult(output="test")
        assert result.observation is None
        with pytest.raises(AttributeError):
            _ = result.observation.preview

    def test_factory_with_observation(self) -> None:
        """工厂方法创建带 observation 的结果"""
        obs = ObservationMetadata(preview="preview text")
        result = ToolResult(output="full text", observation=obs)

        assert result.observation is not None
        assert result.observation.preview == "preview text"


# ============================================================
# ObservationMetadata 边界测试
# ============================================================


class TestObservationMetadataEdgeCases:
    """ObservationMetadata 边界情况测试。"""

    def test_empty_strings(self) -> None:
        """空字符串也是合法值"""
        obs = ObservationMetadata(
            preview="",
            artifact_path="",
        )
        assert obs.preview == ""
        assert obs.artifact_path == ""

    def test_large_full_output_chars(self) -> None:
        """full_output_chars 可以很大"""
        obs = ObservationMetadata(
            preview="short",
            full_output_chars=1_000_000,
        )
        assert obs.full_output_chars == 1_000_000

    def test_unicode_content(self) -> None:
        """支持 Unicode 内容"""
        obs = ObservationMetadata(
            preview="中文预览...",
            artifact_path="/tmp/输出.txt",
        )
        assert obs.preview == "中文预览..."
        assert obs.artifact_path == "/tmp/输出.txt"
