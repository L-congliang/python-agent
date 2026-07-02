"""Worktree 隔离测试"""

from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from agent.tools.subagent import (
    _create_worktree,
    _cleanup_worktree,
    _cleanup_orphaned_worktrees,
)


class TestCreateWorktree:
    """_create_worktree 测试"""

    @patch("subprocess.run")
    def test_create_success(self, mock_run: MagicMock) -> None:
        """成功创建 worktree"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        result = _create_worktree("sa_123456", "/workspace")

        assert result is not None
        assert "sa_123456" in result
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "git" in call_args
        assert "worktree" in call_args
        assert "add" in call_args

    @patch("subprocess.run")
    def test_create_failure(self, mock_run: MagicMock) -> None:
        """创建失败返回 None"""
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        result = _create_worktree("sa_123456", "/workspace")

        assert result is None

    @patch("subprocess.run")
    def test_create_timeout(self, mock_run: MagicMock) -> None:
        """超时返回 None"""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

        result = _create_worktree("sa_123456", "/workspace")

        assert result is None

    @patch("subprocess.run")
    def test_create_git_not_found(self, mock_run: MagicMock) -> None:
        """git 不存在返回 None"""
        mock_run.side_effect = FileNotFoundError

        result = _create_worktree("sa_123456", "/workspace")

        assert result is None


class TestCleanupWorktree:
    """_cleanup_worktree 测试"""

    @patch("subprocess.run")
    def test_cleanup_success(self, mock_run: MagicMock) -> None:
        """成功清理 worktree"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # 不应该抛异常
        _cleanup_worktree("/workspace/.worktrees/sa_123456")

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "git" in call_args
        assert "worktree" in call_args
        assert "remove" in call_args

    @patch("subprocess.run")
    def test_cleanup_failure(self, mock_run: MagicMock) -> None:
        """清理失败不抛异常"""
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        # 不应该抛异常
        _cleanup_worktree("/workspace/.worktrees/sa_123456")

    @patch("subprocess.run")
    def test_cleanup_timeout(self, mock_run: MagicMock) -> None:
        """超时不抛异常"""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

        # 不应该抛异常
        _cleanup_worktree("/workspace/.worktrees/sa_123456")


class TestCleanupOrphanedWorktrees:
    """_cleanup_orphaned_worktrees 测试"""

    @patch("pathlib.Path.exists")
    def test_no_worktrees_dir(self, mock_exists: MagicMock) -> None:
        """没有 .worktrees 目录"""
        mock_exists.return_value = False

        result = _cleanup_orphaned_worktrees("/workspace")

        assert result == 0

    @patch("pathlib.Path.iterdir")
    @patch("pathlib.Path.exists")
    def test_no_orphans(self, mock_exists: MagicMock, mock_iterdir: MagicMock) -> None:
        """没有孤立的 worktree"""
        mock_exists.return_value = True
        mock_iterdir.return_value = []

        result = _cleanup_orphaned_worktrees("/workspace")

        assert result == 0
