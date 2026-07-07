"""Observation Helper 测试

验证 observation_helper 模块的截断逻辑和 artifact 化。
"""

from __future__ import annotations

import os
import tempfile

import pytest

from agent.tools.observation_helper import (
    truncate_output,
    build_observation,
    TruncationResult,
    DEFAULT_MAX_LINES,
    DEFAULT_MAX_CHARS,
)


# ============================================================
# truncate_output 测试
# ============================================================


class TestTruncateOutput:
    """truncate_output 函数测试。"""

    def test_empty_output(self) -> None:
        """空输出"""
        result = truncate_output("")
        assert result.preview == ""
        assert result.was_truncated is False
        assert result.full_lines == 0
        assert result.full_chars == 0

    def test_short_output_no_truncation(self) -> None:
        """短输出不需要截断"""
        output = "line 1\nline 2\nline 3"
        result = truncate_output(output)
        assert result.preview == output
        assert result.was_truncated is False
        assert result.full_lines == 3
        assert result.full_chars == len(output)

    def test_long_output_tail_strategy(self) -> None:
        """长输出，tail 策略（保留尾部）"""
        lines = [f"line {i}" for i in range(100)]
        output = "\n".join(lines)

        result = truncate_output(output, max_lines=10, strategy="tail")

        assert result.was_truncated is True
        assert result.full_lines == 100
        # 保留最后 10 行
        assert "line 99" in result.preview
        assert "line 90" in result.preview
        assert "line 0" not in result.preview
        # 有截断头信息
        assert "truncated" in result.preview

    def test_long_output_head_strategy(self) -> None:
        """长输出，head 策略（保留头部）"""
        lines = [f"line {i}" for i in range(100)]
        output = "\n".join(lines)

        result = truncate_output(output, max_lines=10, strategy="head")

        assert result.was_truncated is True
        assert result.full_lines == 100
        # 保留前 10 行
        assert "line 0" in result.preview
        assert "line 9" in result.preview
        assert "line 99" not in result.preview
        # 没有截断头信息
        assert "truncated" not in result.preview

    def test_char_limit_truncation(self) -> None:
        """字符数限制截断"""
        output = "x" * 1000
        result = truncate_output(output, max_chars=100)

        assert result.was_truncated is True
        assert result.full_chars == 1000
        assert len(result.preview) <= 100

    def test_exactly_at_limit(self) -> None:
        """刚好在限制内"""
        lines = [f"line {i}" for i in range(10)]
        output = "\n".join(lines)

        result = truncate_output(output, max_lines=10)

        assert result.was_truncated is False
        assert result.preview == output

    def test_single_line_long(self) -> None:
        """单行很长"""
        output = "x" * 10000
        result = truncate_output(output, max_chars=100)

        assert result.was_truncated is True
        assert len(result.preview) <= 100


# ============================================================
# build_observation 测试
# ============================================================


class TestBuildObservation:
    """build_observation 函数测试。"""

    def test_short_output_no_artifact(self) -> None:
        """短输出不需要 artifact"""
        output = "short output"
        preview, obs = build_observation(output, tool_name="test")

        assert preview == output
        assert obs.preview == output
        assert obs.was_truncated is False
        assert obs.artifact_path is None
        assert obs.full_output_chars == len(output)

    def test_long_output_with_artifact(self) -> None:
        """长输出保存 artifact"""
        output = "x" * 10000

        with tempfile.TemporaryDirectory() as tmpdir:
            preview, obs = build_observation(
                output,
                tool_name="test",
                artifact_dir=tmpdir,
                max_chars=100,
            )

            assert obs.was_truncated is True
            assert obs.artifact_path is not None
            assert os.path.exists(obs.artifact_path)
            assert obs.full_output_chars == 10000

            # 验证 artifact 内容完整
            with open(obs.artifact_path, encoding="utf-8") as f:
                saved = f.read()
            assert saved == output

    def test_long_output_no_artifact_dir(self) -> None:
        """长输出但没有 artifact_dir"""
        output = "x" * 10000
        preview, obs = build_observation(
            output,
            tool_name="test",
            artifact_dir=None,
            max_chars=100,
        )

        assert obs.was_truncated is True
        assert obs.artifact_path is None

    def test_tail_strategy(self) -> None:
        """tail 策略"""
        lines = [f"line {i}" for i in range(100)]
        output = "\n".join(lines)

        preview, obs = build_observation(
            output,
            tool_name="test",
            max_lines=10,
            strategy="tail",
        )

        assert "line 99" in preview
        assert "line 0" not in preview

    def test_head_strategy(self) -> None:
        """head 策略"""
        lines = [f"line {i}" for i in range(100)]
        output = "\n".join(lines)

        preview, obs = build_observation(
            output,
            tool_name="test",
            max_lines=10,
            strategy="head",
        )

        assert "line 0" in preview
        assert "line 99" not in preview

    def test_unicode_output(self) -> None:
        """Unicode 内容"""
        output = "中文\n" * 1000
        preview, obs = build_observation(
            output,
            tool_name="test",
            max_lines=10,
        )

        assert obs.was_truncated is True
        assert obs.full_output_chars > 0

    def test_empty_output(self) -> None:
        """空输出"""
        preview, obs = build_observation("", tool_name="test")

        assert preview == ""
        assert obs.was_truncated is False
        assert obs.full_output_chars == 0


# ============================================================
# 边界测试
# ============================================================


class TestObservationEdgeCases:
    """边界情况测试。"""

    def test_very_large_output(self) -> None:
        """非常大的输出"""
        output = "x" * 1_000_000
        preview, obs = build_observation(
            output,
            tool_name="test",
            max_chars=1000,
        )

        assert obs.was_truncated is True
        assert obs.full_output_chars == 1_000_000
        assert len(preview) <= 1000

    def test_many_lines(self) -> None:
        """很多行"""
        lines = [f"line {i}" for i in range(10000)]
        output = "\n".join(lines)

        preview, obs = build_observation(
            output,
            tool_name="test",
            max_lines=100,
        )

        assert obs.was_truncated is True
        assert obs.full_output_chars > 0

    def test_artifact_dir_not_exist(self) -> None:
        """artifact_dir 不存在时自动创建"""
        output = "x" * 10000

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = os.path.join(tmpdir, "subdir")
            preview, obs = build_observation(
                output,
                tool_name="test",
                artifact_dir=artifact_dir,
                max_chars=100,
            )

            assert obs.artifact_path is not None
            assert os.path.exists(obs.artifact_path)
