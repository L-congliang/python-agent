"""Observation Integration 测试

验证真实工具执行 -> artifact 生成 -> loop/CLI 可见的完整链路。
"""

from __future__ import annotations

import os
import tempfile

import pytest

from agent.core.context import ToolUseContext, AbortController, FileReadState
from agent.core.types import ToolResult
from agent.tools.observation_helper import build_observation


# ============================================================
# 辅助函数
# ============================================================


def create_test_context(artifact_dir: str | None = None) -> ToolUseContext:
    """创建测试用的 ToolUseContext"""
    return ToolUseContext(
        model="test",
        artifact_dir=artifact_dir,
    )


# ============================================================
# build_observation 集成测试
# ============================================================


class TestBuildObservationIntegration:
    """build_observation 与真实 artifact 目录集成测试。"""

    def test_artifact_saved_when_dir_provided(self) -> None:
        """提供 artifact_dir 时，长输出应该保存到文件"""
        output = "x" * 10000  # 超过默认阈值

        with tempfile.TemporaryDirectory() as tmpdir:
            preview, obs = build_observation(
                output=output,
                tool_name="bash",
                artifact_dir=tmpdir,
                max_chars=100,
            )

            # 验证 artifact 被保存
            assert obs.was_truncated is True
            assert obs.artifact_path is not None
            assert os.path.exists(obs.artifact_path)

            # 验证 artifact 内容完整
            with open(obs.artifact_path, encoding="utf-8") as f:
                saved_content = f.read()
            assert saved_content == output

            # 验证 preview 是截断版本
            assert len(preview) <= 100

    def test_artifact_not_saved_when_dir_none(self) -> None:
        """artifact_dir 为 None 时，不保存 artifact"""
        output = "x" * 10000

        preview, obs = build_observation(
            output=output,
            tool_name="bash",
            artifact_dir=None,
            max_chars=100,
        )

        assert obs.was_truncated is True
        assert obs.artifact_path is None

    def test_artifact_not_saved_when_short_output(self) -> None:
        """短输出不保存 artifact"""
        output = "short"

        with tempfile.TemporaryDirectory() as tmpdir:
            preview, obs = build_observation(
                output=output,
                tool_name="bash",
                artifact_dir=tmpdir,
                max_chars=100,
            )

            assert obs.was_truncated is False
            assert obs.artifact_path is None

    def test_artifact_filename_includes_tool_name(self) -> None:
        """artifact 文件名包含工具名"""
        output = "x" * 10000

        with tempfile.TemporaryDirectory() as tmpdir:
            preview, obs = build_observation(
                output=output,
                tool_name="grep",
                artifact_dir=tmpdir,
                max_chars=100,
            )

            assert obs.artifact_path is not None
            assert "grep" in os.path.basename(obs.artifact_path)

    def test_artifact_subdirectory_created(self) -> None:
        """artifact_dir 不存在时自动创建"""
        output = "x" * 10000

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = os.path.join(tmpdir, "subdir1", "subdir2")
            preview, obs = build_observation(
                output=output,
                tool_name="bash",
                artifact_dir=artifact_dir,
                max_chars=100,
            )

            assert obs.artifact_path is not None
            assert os.path.exists(obs.artifact_path)


# ============================================================
# ToolUseContext artifact_dir 测试
# ============================================================


class TestToolUseContextArtifactDir:
    """ToolUseContext 的 artifact_dir 字段测试。"""

    def test_default_artifact_dir_none(self) -> None:
        """默认 artifact_dir 为 None"""
        context = create_test_context()
        assert context.artifact_dir is None

    def test_custom_artifact_dir(self) -> None:
        """自定义 artifact_dir"""
        context = create_test_context(artifact_dir="/tmp/artifacts")
        assert context.artifact_dir == "/tmp/artifacts"


# ============================================================
# 边界测试
# ============================================================


class TestObservationIntegrationEdgeCases:
    """边界情况测试。"""

    def test_unicode_artifact(self) -> None:
        """Unicode 内容保存到 artifact"""
        output = "中文内容\n" * 1000

        with tempfile.TemporaryDirectory() as tmpdir:
            preview, obs = build_observation(
                output=output,
                tool_name="read",
                artifact_dir=tmpdir,
                max_chars=100,
            )

            assert obs.artifact_path is not None
            with open(obs.artifact_path, encoding="utf-8") as f:
                saved = f.read()
            assert saved == output

    def test_large_artifact(self) -> None:
        """大文件保存到 artifact"""
        output = "x" * 1_000_000

        with tempfile.TemporaryDirectory() as tmpdir:
            preview, obs = build_observation(
                output=output,
                tool_name="bash",
                artifact_dir=tmpdir,
                max_chars=1000,
            )

            assert obs.artifact_path is not None
            assert os.path.getsize(obs.artifact_path) == 1_000_000

    def test_multiple_artifacts(self) -> None:
        """多次调用生成多个 artifact"""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                output = f"output_{i}" * 1000
                preview, obs = build_observation(
                    output=output,
                    tool_name=f"tool_{i}",
                    artifact_dir=tmpdir,
                    max_chars=100,
                )
                assert obs.artifact_path is not None

            # 验证生成了 3 个文件
            files = os.listdir(tmpdir)
            assert len(files) == 3
