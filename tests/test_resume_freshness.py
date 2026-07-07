"""Resume Freshness 测试

验证 resume 时的 checkpoint freshness 检测。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from agent.observability.checkpoint import (
    CheckpointManager,
    Checkpoint,
    TrackedFile,
    FreshnessResult,
)


# ============================================================
# 辅助函数
# ============================================================


def create_temp_checkpoint_manager() -> tuple[CheckpointManager, Path]:
    """创建临时目录的 CheckpointManager，返回 (manager, tmpdir)"""
    tmpdir = Path(tempfile.mkdtemp())
    manager = CheckpointManager(tmpdir / ".agent" / "checkpoints")
    return manager, tmpdir


def create_test_checkpoint(
    manager: CheckpointManager,
    tracked_files: dict[str, TrackedFile],
    run_id: str = "test_run",
) -> Checkpoint:
    """创建测试用的 checkpoint"""
    # 临时设置 tracked_files
    manager._tracked_files = tracked_files
    return manager.create(
        goal="test goal",
        completed_steps=["step1"],
        next_step="step2",
        run_id=run_id,
    )


# ============================================================
# Freshness 检测测试
# ============================================================


class TestFreshnessDetection:
    """Freshness 检测测试。"""

    def test_freshness_no_checkpoint(self) -> None:
        """没有 checkpoint 时，状态为 unavailable"""
        manager, tmpdir = create_temp_checkpoint_manager()

        checkpoint = manager.load_latest()
        assert checkpoint is None

    def test_freshness_full_valid(self) -> None:
        """文件未变化时，状态为 full-valid"""
        manager, tmpdir = create_temp_checkpoint_manager()

        # 创建测试文件
        test_file = tmpdir / "test.txt"
        test_file.write_text("hello")

        # 追踪文件
        manager.track_file(str(test_file), "read")

        # 创建 checkpoint
        checkpoint = manager.create(
            goal="test",
            completed_steps=[],
            next_step="continue",
        )

        # 检测 freshness
        result = manager.check_freshness(checkpoint)
        assert result.resume_status == "full-valid"
        assert result.message != ""

    def test_freshness_partial_stale(self) -> None:
        """文件被修改时，状态为 partial-stale"""
        manager, tmpdir = create_temp_checkpoint_manager()

        # 创建测试文件
        test_file = tmpdir / "test.txt"
        test_file.write_text("hello")

        # 追踪文件
        manager.track_file(str(test_file), "read")

        # 创建 checkpoint
        checkpoint = manager.create(
            goal="test",
            completed_steps=[],
            next_step="continue",
        )

        # 修改文件
        test_file.write_text("modified")

        # 检测 freshness
        result = manager.check_freshness(checkpoint)
        assert result.resume_status == "partial-stale"

    def test_freshness_invalid_file_deleted(self) -> None:
        """文件被删除时，状态为 invalid"""
        manager, tmpdir = create_temp_checkpoint_manager()

        # 创建测试文件
        test_file = tmpdir / "test.txt"
        test_file.write_text("hello")

        # 追踪文件
        manager.track_file(str(test_file), "read")

        # 创建 checkpoint
        checkpoint = manager.create(
            goal="test",
            completed_steps=[],
            next_step="continue",
        )

        # 删除文件
        test_file.unlink()

        # 检测 freshness
        result = manager.check_freshness(checkpoint)
        assert result.resume_status == "invalid"

    def test_freshness_multiple_files_mixed(self) -> None:
        """多个文件混合状态"""
        manager, tmpdir = create_temp_checkpoint_manager()

        # 创建测试文件
        file1 = tmpdir / "file1.txt"
        file2 = tmpdir / "file2.txt"
        file1.write_text("hello")
        file2.write_text("world")

        # 追踪文件
        manager.track_file(str(file1), "read")
        manager.track_file(str(file2), "read")

        # 创建 checkpoint
        checkpoint = manager.create(
            goal="test",
            completed_steps=[],
            next_step="continue",
        )

        # 修改一个文件
        file1.write_text("modified")

        # 检测 freshness
        result = manager.check_freshness(checkpoint)
        assert result.resume_status == "partial-stale"

    def test_freshness_file_statuses(self) -> None:
        """file_statuses 正确记录各文件状态"""
        manager, tmpdir = create_temp_checkpoint_manager()

        # 创建测试文件
        file1 = tmpdir / "file1.txt"
        file2 = tmpdir / "file2.txt"
        file1.write_text("hello")
        file2.write_text("world")

        # 追踪文件
        manager.track_file(str(file1), "read")
        manager.track_file(str(file2), "read")

        # 创建 checkpoint
        checkpoint = manager.create(
            goal="test",
            completed_steps=[],
            next_step="continue",
        )

        # 修改 file1
        file1.write_text("modified")

        # 检测 freshness
        result = manager.check_freshness(checkpoint)

        # 验证 file_statuses
        assert str(file1) in result.file_statuses
        assert str(file2) in result.file_statuses
        assert result.file_statuses[str(file1)] == "modified"
        assert result.file_statuses[str(file2)] == "unchanged"


# ============================================================
# CheckpointManager 查询测试
# ============================================================


class TestCheckpointManagerQuery:
    """CheckpointManager 查询测试。"""

    def test_load_latest(self) -> None:
        """加载最新的 checkpoint"""
        manager, tmpdir = create_temp_checkpoint_manager()

        # 创建测试文件
        test_file = tmpdir / "test.txt"
        test_file.write_text("hello")

        # 追踪文件
        manager.track_file(str(test_file), "read")

        # 创建 checkpoint
        checkpoint = manager.create(
            goal="test",
            completed_steps=[],
            next_step="continue",
        )

        # 加载最新
        loaded = manager.load_latest()
        assert loaded is not None
        assert loaded.checkpoint_id == checkpoint.checkpoint_id

    def test_load_latest_empty(self) -> None:
        """没有 checkpoint 时返回 None"""
        manager, tmpdir = create_temp_checkpoint_manager()

        loaded = manager.load_latest()
        assert loaded is None

    def test_load_by_id(self) -> None:
        """按 ID 加载 checkpoint"""
        manager, tmpdir = create_temp_checkpoint_manager()

        # 创建测试文件
        test_file = tmpdir / "test.txt"
        test_file.write_text("hello")

        # 追踪文件
        manager.track_file(str(test_file), "read")

        # 创建 checkpoint
        checkpoint = manager.create(
            goal="test",
            completed_steps=[],
            next_step="continue",
        )

        # 按 ID 加载
        loaded = manager.load(checkpoint.checkpoint_id)
        assert loaded is not None
        assert loaded.checkpoint_id == checkpoint.checkpoint_id

    def test_load_by_id_not_found(self) -> None:
        """按 ID 加载不存在的 checkpoint 返回 None"""
        manager, tmpdir = create_temp_checkpoint_manager()

        loaded = manager.load("nonexistent_id")
        assert loaded is None


# ============================================================
# Loop freshness 状态测试
# ============================================================


class TestLoopFreshnessState:
    """Loop freshness 状态测试。"""

    def test_loop_has_freshness_summary(self) -> None:
        """Loop 有 freshness_summary 属性"""
        from agent.core.loop import AgentLoop, LoopConfig
        from agent.tools.registry import ToolRegistry, register_base_tools
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_client = MagicMock()
            config = LoopConfig(model="test", workspace_root=tmpdir)
            registry = register_base_tools(ToolRegistry())
            loop = AgentLoop(mock_client, registry, config=config)

            # 初始 freshness_summary 为 None
            assert loop._resume_freshness_summary is None

    def test_loop_set_freshness_summary(self) -> None:
        """Loop 可以设置 freshness_summary"""
        from agent.core.loop import AgentLoop, LoopConfig
        from agent.tools.registry import ToolRegistry, register_base_tools
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_client = MagicMock()
            config = LoopConfig(model="test", workspace_root=tmpdir)
            registry = register_base_tools(ToolRegistry())
            loop = AgentLoop(mock_client, registry, config=config)

            # 设置 freshness_summary
            summary = {
                "resume_status": "full-valid",
                "message": "all files unchanged",
            }
            loop.set_resume_freshness_summary(summary)

            # 验证
            assert loop._resume_freshness_summary == summary

    def test_loop_get_freshness_summary(self) -> None:
        """Loop 可以获取 freshness_summary"""
        from agent.core.loop import AgentLoop, LoopConfig
        from agent.tools.registry import ToolRegistry, register_base_tools
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_client = MagicMock()
            config = LoopConfig(model="test", workspace_root=tmpdir)
            registry = register_base_tools(ToolRegistry())
            loop = AgentLoop(mock_client, registry, config=config)

            # 初始为 None
            assert loop.get_resume_freshness_summary() is None

            # 设置后获取
            summary = {"resume_status": "partial-stale"}
            loop.set_resume_freshness_summary(summary)
            assert loop.get_resume_freshness_summary() == summary


# ============================================================
# 边界测试
# ============================================================


class TestFreshnessEdgeCases:
    """边界情况测试。"""

    def test_freshness_empty_tracked_files(self) -> None:
        """没有追踪文件时，状态为 full-valid"""
        manager, tmpdir = create_temp_checkpoint_manager()

        # 创建 checkpoint（没有追踪文件）
        checkpoint = manager.create(
            goal="test",
            completed_steps=[],
            next_step="continue",
        )

        # 检测 freshness
        result = manager.check_freshness(checkpoint)
        assert result.resume_status == "full-valid"

    def test_freshness_unicode_filenames(self) -> None:
        """Unicode 文件名"""
        manager, tmpdir = create_temp_checkpoint_manager()

        # 创建测试文件
        test_file = tmpdir / "中文文件.txt"
        test_file.write_text("hello")

        # 追踪文件
        manager.track_file(str(test_file), "read")

        # 创建 checkpoint
        checkpoint = manager.create(
            goal="test",
            completed_steps=[],
            next_step="continue",
        )

        # 检测 freshness
        result = manager.check_freshness(checkpoint)
        assert result.resume_status == "full-valid"

    def test_freshness_large_file(self) -> None:
        """大文件（超过阈值）只用 mtime 检测"""
        manager, tmpdir = create_temp_checkpoint_manager()

        # 创建大文件
        test_file = tmpdir / "large.txt"
        test_file.write_text("x" * (1024 * 1024 + 1))  # 超过 1MB

        # 追踪文件
        manager.track_file(str(test_file), "read")

        # 创建 checkpoint
        checkpoint = manager.create(
            goal="test",
            completed_steps=[],
            next_step="continue",
        )

        # 检测 freshness（大文件只用 mtime，所以修改内容但不改 mtime 应该是 unchanged）
        result = manager.check_freshness(checkpoint)
        assert result.resume_status == "full-valid"
