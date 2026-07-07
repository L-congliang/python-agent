"""Session Autosave 测试

验证 session 自动保存、/reset 后新 session、--resume 后继续保存。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.core.loop import AgentLoop, LoopConfig
from agent.core.types import ToolCall, ToolResult
from agent.persistence.session_store import SessionStore
from agent.tools.registry import ToolRegistry, register_base_tools


# ============================================================
# 辅助函数
# ============================================================


def create_test_loop(
    tmpdir: str,
    enable_autosave: bool = True,
) -> tuple[AgentLoop, SessionStore]:
    """创建测试用的 AgentLoop，返回 (loop, session_store)"""
    mock_client = MagicMock()
    session_dir = os.path.join(tmpdir, ".agent", "sessions")

    config = LoopConfig(
        model="test",
        workspace_root=tmpdir,
        session_dir=session_dir,
        enable_autosave=enable_autosave,
    )
    registry = register_base_tools(ToolRegistry())
    loop = AgentLoop(mock_client, registry, config=config)

    session_store = loop._session_store
    return loop, session_store


# ============================================================
# Autosave 装配测试
# ============================================================


class TestAutosaveWiring:
    """Autosave 装配测试。"""

    def test_loop_has_session_store(self) -> None:
        """默认入口创建 loop 时，会自动挂上 SessionStore"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, store = create_test_loop(tmpdir)
            assert store is not None
            assert loop._session_store is not None

    def test_loop_has_session_id_none(self) -> None:
        """初始 session_id 为 None"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, _ = create_test_loop(tmpdir)
            assert loop._session_id is None

    def test_loop_enable_autosave_config(self) -> None:
        """enable_autosave 配置生效"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, _ = create_test_loop(tmpdir, enable_autosave=True)
            assert loop._config.enable_autosave is True

            loop2, _ = create_test_loop(tmpdir, enable_autosave=False)
            assert loop2._config.enable_autosave is False


# ============================================================
# Autosave 行为测试
# ============================================================


class TestAutosaveBehavior:
    """Autosave 行为测试。"""

    def test_save_session_creates_file(self) -> None:
        """save_session 创建 session 文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, store = create_test_loop(tmpdir)

            # 手动添加一些消息
            loop._messages = [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ]

            # 保存 session
            session_id = loop.save_session()

            # 验证文件存在
            assert session_id is not None
            file_path = store._session_dir / f"{session_id}.json"
            assert file_path.exists()

    def test_save_session_preserves_messages(self) -> None:
        """save_session 保留消息历史"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, store = create_test_loop(tmpdir)

            # 添加消息
            loop._messages = [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ]

            # 保存
            session_id = loop.save_session()

            # 加载并验证
            data = store.load(session_id)
            assert data is not None
            assert len(data["messages"]) == 2
            assert data["messages"][0]["content"] == "hello"

    def test_save_session_sets_session_id(self) -> None:
        """save_session 设置 session_id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, _ = create_test_loop(tmpdir)

            assert loop._session_id is None

            # 保存
            session_id = loop.save_session()

            assert loop._session_id == session_id

    def test_save_session_overwrites_existing(self) -> None:
        """连续保存覆盖更新同一个 session"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, store = create_test_loop(tmpdir)

            # 第一次保存
            loop._messages = [{"role": "user", "content": "first"}]
            session_id_1 = loop.save_session()

            # 第二次保存
            loop._messages = [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "response"},
                {"role": "user", "content": "second"},
            ]
            session_id_2 = loop.save_session()

            # 应该是同一个 session_id
            assert session_id_1 == session_id_2

            # 文件内容应该是最新的
            data = store.load(session_id_1)
            assert data is not None
            assert len(data["messages"]) == 3

    def test_save_session_disabled(self) -> None:
        """disable autosave 时 save_session 返回 None"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, _ = create_test_loop(tmpdir, enable_autosave=False)

            # save_session 应该返回 None
            result = loop.save_session()
            assert result is None


# ============================================================
# Reset 行为测试
# ============================================================


class TestResetBehavior:
    """Reset 行为测试。"""

    def test_reset_clears_session_id(self) -> None:
        """reset 后 session_id 置空"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, _ = create_test_loop(tmpdir)

            # 保存一个 session
            loop._messages = [{"role": "user", "content": "hello"}]
            loop.save_session()
            assert loop._session_id is not None

            # reset
            loop.reset()

            # session_id 应该置空
            assert loop._session_id is None

    def test_reset_preserves_old_session(self) -> None:
        """reset 后旧 session 文件保留"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, store = create_test_loop(tmpdir)

            # 保存一个 session
            loop._messages = [{"role": "user", "content": "hello"}]
            old_session_id = loop.save_session()

            # reset
            loop.reset()

            # 旧 session 文件应该还在
            data = store.load(old_session_id)
            assert data is not None

    def test_reset_then_save_creates_new_session(self) -> None:
        """reset 后保存创建新 session"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, store = create_test_loop(tmpdir)

            # 保存第一个 session
            loop._messages = [{"role": "user", "content": "first"}]
            first_session_id = loop.save_session()

            # reset
            loop.reset()

            # 保存第二个 session
            loop._messages = [{"role": "user", "content": "second"}]
            second_session_id = loop.save_session()

            # 应该是不同的 session_id
            assert first_session_id != second_session_id

            # 两个 session 都存在
            assert store.load(first_session_id) is not None
            assert store.load(second_session_id) is not None


# ============================================================
# Resume 行为测试
# ============================================================


class TestResumeBehavior:
    """Resume 行为测试。"""

    def test_resume_then_save_updates_same_session(self) -> None:
        """resume 后继续保存更新同一个 session"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, store = create_test_loop(tmpdir)

            # 保存第一个 session
            loop._messages = [{"role": "user", "content": "first"}]
            original_session_id = loop.save_session()

            # reset
            loop.reset()

            # resume
            data = store.load(original_session_id)
            loop.import_session_state(data)

            # 继续对话
            loop._messages.append({"role": "assistant", "content": "response"})
            resumed_session_id = loop.save_session()

            # 应该是同一个 session_id
            assert resumed_session_id == original_session_id

            # 内容应该是更新后的
            updated_data = store.load(original_session_id)
            assert updated_data is not None
            assert len(updated_data["messages"]) == 2

    def test_resume_preserves_session_id(self) -> None:
        """import_session_state 后 session_id 保持不变"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, _ = create_test_loop(tmpdir)

            # 模拟 session state
            state = {
                "session_id": "test_session_123",
                "messages": [{"role": "user", "content": "hello"}],
            }

            # 导入
            loop.import_session_state(state)

            # session_id 应该保持
            assert loop._session_id == "test_session_123"


# ============================================================
# 边界测试
# ============================================================


class TestAutosaveEdgeCases:
    """边界情况测试。"""

    def test_unicode_messages(self) -> None:
        """Unicode 消息自动保存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, store = create_test_loop(tmpdir)

            loop._messages = [
                {"role": "user", "content": "中文消息"},
                {"role": "assistant", "content": "回复中文"},
            ]

            session_id = loop.save_session()
            data = store.load(session_id)

            assert data is not None
            assert data["messages"][0]["content"] == "中文消息"

    def test_empty_messages(self) -> None:
        """空消息列表自动保存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, _ = create_test_loop(tmpdir)

            loop._messages = []
            session_id = loop.save_session()

            assert session_id is not None

    def test_large_messages(self) -> None:
        """大量消息自动保存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, store = create_test_loop(tmpdir)

            loop._messages = [
                {"role": "user", "content": f"message {i}"} for i in range(100)
            ]

            session_id = loop.save_session()
            data = store.load(session_id)

            assert data is not None
            assert len(data["messages"]) == 100
