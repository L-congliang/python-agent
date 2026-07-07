"""Session Resume 测试

验证 session 持久化、恢复和 --resume 参数。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from agent.persistence.session_store import SessionStore


# ============================================================
# 辅助函数
# ============================================================


def create_temp_store() -> tuple[SessionStore, Path]:
    """创建临时目录的 store，返回 (store, tmpdir)"""
    tmpdir = Path(tempfile.mkdtemp())
    store = SessionStore(tmpdir / ".agent" / "sessions")
    return store, tmpdir


# ============================================================
# SessionStore 二层结构测试
# ============================================================


class TestSessionStoreTwoLayer:
    """SessionStore 二层结构测试。"""

    def test_save_creates_resumable_file(self) -> None:
        """保存时创建可恢复文件（raw data）"""
        store, tmpdir = create_temp_store()

        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

        session_id = store.save(messages=messages)

        # 验证文件存在
        file_path = store._session_dir / f"{session_id}.json"
        assert file_path.exists()

        # 验证内容是原始数据（未脱敏）
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["id"] == session_id
        assert "messages" in data
        assert len(data["messages"]) == 2

    def test_save_with_memory(self) -> None:
        """保存时包含 memory"""
        store, tmpdir = create_temp_store()

        messages = [{"role": "user", "content": "hello"}]
        memory = {"task": "test task", "notes": ["note1", "note2"]}

        session_id = store.save(messages=messages, memory=memory)

        # 加载并验证
        data = store.load(session_id)
        assert data is not None
        assert data["memory"]["task"] == "test task"
        assert len(data["memory"]["notes"]) == 2

    def test_save_with_workspace_root(self) -> None:
        """保存时包含 workspace_root"""
        store, tmpdir = create_temp_store()

        messages = [{"role": "user", "content": "hello"}]
        workspace_root = "/path/to/workspace"

        session_id = store.save(messages=messages, workspace_root=workspace_root)

        # 加载并验证
        data = store.load(session_id)
        assert data is not None
        assert data["workspace_root"] == workspace_root

    def test_save_with_session_id(self) -> None:
        """使用指定 session_id 保存"""
        store, tmpdir = create_temp_store()

        messages = [{"role": "user", "content": "hello"}]
        session_id = "my_custom_session"

        result_id = store.save(messages=messages, session_id=session_id)

        assert result_id == session_id

        # 加载并验证
        data = store.load(session_id)
        assert data is not None
        assert data["id"] == session_id


# ============================================================
# load / load_latest 测试
# ============================================================


class TestSessionLoad:
    """Session 加载测试。"""

    def test_load_existing_session(self) -> None:
        """加载存在的 session"""
        store, tmpdir = create_temp_store()

        messages = [{"role": "user", "content": "hello"}]
        session_id = store.save(messages=messages)

        data = store.load(session_id)
        assert data is not None
        assert data["id"] == session_id
        assert len(data["messages"]) == 1

    def test_load_nonexistent_session(self) -> None:
        """加载不存在的 session 返回 None"""
        store, tmpdir = create_temp_store()

        data = store.load("nonexistent_session")
        assert data is None

    def test_load_latest(self) -> None:
        """加载最新的 session"""
        store, tmpdir = create_temp_store()

        # 保存两个 session（使用不同时间戳）
        store.save(messages=[{"role": "user", "content": "first"}], session_id="session_1")

        # 修改第一个文件的时间戳，让它更旧
        file1 = store._session_dir / "session_1.json"
        old_time = file1.stat().st_mtime - 10
        os.utime(file1, (old_time, old_time))

        store.save(messages=[{"role": "user", "content": "second"}], session_id="session_2")

        # 加载最新
        data = store.load_latest()
        assert data is not None
        # 最新的应该是最后保存的
        assert data["id"] == "session_2"

    def test_load_latest_empty(self) -> None:
        """没有 session 时返回 None"""
        store, tmpdir = create_temp_store()

        data = store.load_latest()
        assert data is None


# ============================================================
# list_sessions 测试
# ============================================================


class TestSessionList:
    """Session 列表测试。"""

    def test_list_sessions(self) -> None:
        """列出所有 session"""
        store, tmpdir = create_temp_store()

        # 保存两个 session
        store.save(messages=[{"role": "user", "content": "first"}], session_id="session_1")
        store.save(messages=[{"role": "user", "content": "second"}], session_id="session_2")

        sessions = store.list_sessions()
        assert len(sessions) == 2

        # 验证摘要字段
        for s in sessions:
            assert "id" in s
            assert "created_at" in s
            assert "message_count" in s

    def test_list_sessions_empty(self) -> None:
        """没有 session 时返回空列表"""
        store, tmpdir = create_temp_store()

        sessions = store.list_sessions()
        assert sessions == []


# ============================================================
# delete 测试
# ============================================================


class TestSessionDelete:
    """Session 删除测试。"""

    def test_delete_existing_session(self) -> None:
        """删除存在的 session"""
        store, tmpdir = create_temp_store()

        session_id = store.save(messages=[{"role": "user", "content": "hello"}])

        # 删除
        result = store.delete(session_id)
        assert result is True

        # 验证已删除
        data = store.load(session_id)
        assert data is None

    def test_delete_nonexistent_session(self) -> None:
        """删除不存在的 session 返回 False"""
        store, tmpdir = create_temp_store()

        result = store.delete("nonexistent_session")
        assert result is False


# ============================================================
# resume 场景测试
# ============================================================


class TestSessionResume:
    """Session resume 场景测试。"""

    def test_resume_preserves_messages(self) -> None:
        """resume 保留消息历史"""
        store, tmpdir = create_temp_store()

        # 保存带有多轮消息的 session
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "how are you?"},
            {"role": "assistant", "content": "I'm fine."},
        ]
        session_id = store.save(messages=messages)

        # resume
        data = store.load(session_id)
        assert data is not None
        assert len(data["messages"]) == 4
        assert data["messages"][0]["content"] == "hello"
        assert data["messages"][3]["content"] == "I'm fine."

    def test_resume_preserves_memory(self) -> None:
        """resume 保留 memory"""
        store, tmpdir = create_temp_store()

        messages = [{"role": "user", "content": "hello"}]
        memory = {"task": "build a website", "preferences": ["Python", "FastAPI"]}
        session_id = store.save(messages=messages, memory=memory)

        # resume
        data = store.load(session_id)
        assert data is not None
        assert data["memory"]["task"] == "build a website"
        assert "Python" in data["memory"]["preferences"]

    def test_resume_latest(self) -> None:
        """resume latest 获取最新 session"""
        store, tmpdir = create_temp_store()

        # 保存两个 session
        store.save(
            messages=[{"role": "user", "content": "first"}],
            session_id="session_old",
        )
        store.save(
            messages=[{"role": "user", "content": "second"}],
            session_id="session_new",
        )

        # resume latest
        data = store.load_latest()
        assert data is not None
        assert data["id"] == "session_new"
        assert data["messages"][0]["content"] == "second"

    def test_resume_no_session_graceful(self) -> None:
        """没有 session 时 resume latest 优雅失败"""
        store, tmpdir = create_temp_store()

        data = store.load_latest()
        assert data is None  # 不崩溃，返回 None


# ============================================================
# 边界测试
# ============================================================


class TestSessionEdgeCases:
    """边界情况测试。"""

    def test_unicode_messages(self) -> None:
        """Unicode 消息"""
        store, tmpdir = create_temp_store()

        messages = [
            {"role": "user", "content": "中文消息"},
            {"role": "assistant", "content": "回复中文"},
        ]
        session_id = store.save(messages=messages)

        data = store.load(session_id)
        assert data is not None
        assert data["messages"][0]["content"] == "中文消息"

    def test_large_messages(self) -> None:
        """大量消息"""
        store, tmpdir = create_temp_store()

        messages = [{"role": "user", "content": f"message {i}"} for i in range(100)]
        session_id = store.save(messages=messages)

        data = store.load(session_id)
        assert data is not None
        assert len(data["messages"]) == 100

    def test_empty_messages(self) -> None:
        """空消息列表"""
        store, tmpdir = create_temp_store()

        session_id = store.save(messages=[])

        data = store.load(session_id)
        assert data is not None
        assert data["messages"] == []

    def test_session_id_format(self) -> None:
        """session_id 格式"""
        store, tmpdir = create_temp_store()

        session_id = store.save(messages=[{"role": "user", "content": "hello"}])

        # 验证格式
        assert session_id.startswith("session_")
        assert len(session_id) > 8
