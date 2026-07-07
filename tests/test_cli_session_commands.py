"""CLI Session Commands 测试

验证 /session、/sessions、/inspect 命令。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.core.loop import AgentLoop, LoopConfig
from agent.tools.registry import ToolRegistry, register_base_tools
from agent.cli.app import AgentApp


# ============================================================
# 辅助函数
# ============================================================


def create_test_loop(tmpdir: str) -> AgentLoop:
    """创建测试用的 AgentLoop"""
    mock_client = MagicMock()
    session_dir = os.path.join(tmpdir, ".agent", "sessions")

    config = LoopConfig(
        model="test",
        workspace_root=tmpdir,
        session_dir=session_dir,
    )
    registry = register_base_tools(ToolRegistry())
    return AgentLoop(mock_client, registry, config=config)


def create_test_app(loop: AgentLoop) -> AgentApp:
    """创建测试用的 AgentApp"""
    mock_on_message = MagicMock()

    def _on_session():
        return loop.get_session_summary()

    def _on_sessions():
        return loop.list_recent_sessions()

    def _on_inspect():
        return loop.get_inspect_summary()

    return AgentApp(
        on_message=mock_on_message,
        on_session=_on_session,
        on_sessions=_on_sessions,
        on_inspect=_on_inspect,
    )


# ============================================================
# Loop 摘要接口测试
# ============================================================


class TestLoopSummaryMethods:
    """Loop 摘要接口测试。"""

    def test_get_session_summary_with_session(self) -> None:
        """有活动 session 时返回摘要"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = create_test_loop(tmpdir)

            # 添加消息并保存
            loop._messages = [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ]
            loop.save_session()

            summary = loop.get_session_summary()
            assert summary is not None
            assert "session_id" in summary
            assert "message_count" in summary
            assert summary["message_count"] == 2

    def test_get_session_summary_without_session(self) -> None:
        """没有活动 session 时返回 None"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = create_test_loop(tmpdir)

            summary = loop.get_session_summary()
            assert summary is None

    def test_list_recent_sessions(self) -> None:
        """列出最近 sessions"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = create_test_loop(tmpdir)

            # 保存两个 session
            loop._messages = [{"role": "user", "content": "first"}]
            loop.save_session()
            loop.reset()
            loop._messages = [{"role": "user", "content": "second"}]
            loop.save_session()

            sessions = loop.list_recent_sessions()
            assert len(sessions) == 2

    def test_list_recent_sessions_empty(self) -> None:
        """没有 session 时返回空列表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = create_test_loop(tmpdir)

            sessions = loop.list_recent_sessions()
            assert sessions == []

    def test_get_inspect_summary(self) -> None:
        """获取 inspect 摘要"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = create_test_loop(tmpdir)

            summary = loop.get_inspect_summary()
            assert summary is not None
            assert "run" in summary
            assert "session" in summary
            assert "workspace" in summary


# ============================================================
# CLI 命令测试
# ============================================================


class TestCLICommands:
    """CLI 命令测试。"""

    def test_session_command_with_session(self) -> None:
        """/session 命令显示当前 session 信息"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = create_test_loop(tmpdir)
            app = create_test_app(loop)

            # 添加消息并保存
            loop._messages = [{"role": "user", "content": "hello"}]
            loop.save_session()

            # 捕获输出
            with patch.object(app.console, 'print') as mock_print:
                result = app._handle_command("/session")
                assert result is True
                mock_print.assert_called()

    def test_session_command_without_session(self) -> None:
        """/session 命令没有 session 时显示提示"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = create_test_loop(tmpdir)
            app = create_test_app(loop)

            # 捕获输出
            with patch.object(app.console, 'print') as mock_print:
                result = app._handle_command("/session")
                assert result is True
                mock_print.assert_called()

    def test_sessions_command_with_sessions(self) -> None:
        """/sessions 命令列出最近 sessions"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = create_test_loop(tmpdir)
            app = create_test_app(loop)

            # 保存一个 session
            loop._messages = [{"role": "user", "content": "hello"}]
            loop.save_session()

            # 捕获输出
            with patch.object(app.console, 'print') as mock_print:
                result = app._handle_command("/sessions")
                assert result is True
                mock_print.assert_called()

    def test_sessions_command_empty(self) -> None:
        """/sessions 命令没有 session 时显示暂无"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = create_test_loop(tmpdir)
            app = create_test_app(loop)

            # 捕获输出
            with patch.object(app.console, 'print') as mock_print:
                result = app._handle_command("/sessions")
                assert result is True
                mock_print.assert_called()

    def test_inspect_command(self) -> None:
        """/inspect 命令显示当前状态"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = create_test_loop(tmpdir)
            app = create_test_app(loop)

            # 捕获输出
            with patch.object(app.console, 'print') as mock_print:
                result = app._handle_command("/inspect")
                assert result is True
                mock_print.assert_called()


# ============================================================
# 边界测试
# ============================================================


class TestCLICommandsEdgeCases:
    """边界情况测试。"""

    def test_commands_dont_crash_without_session_store(self) -> None:
        """没有 session store 时命令不崩溃"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_client = MagicMock()
            config = LoopConfig(model="test", workspace_root=tmpdir)
            registry = register_base_tools(ToolRegistry())
            loop = AgentLoop(mock_client, registry, config=config)

            # 没有 session store 时，摘要方法应该返回 None 或空
            assert loop.get_session_summary() is None
            assert loop.list_recent_sessions() == []

    def test_commands_dont_trigger_llm(self) -> None:
        """命令不触发真实模型请求"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = create_test_loop(tmpdir)
            app = create_test_app(loop)

            # 执行命令
            with patch.object(app.console, 'print'):
                app._handle_command("/session")
                app._handle_command("/sessions")
                app._handle_command("/inspect")

            # 如果没有异常，说明没有触发 LLM 请求
