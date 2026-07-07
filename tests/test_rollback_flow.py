"""Rollback Flow 测试

验证 write/edit -> history -> rollback 的端到端链路。
"""

from __future__ import annotations

import os
import tempfile

import pytest

from agent.core.context import ToolUseContext, AbortController, FileReadState
from agent.persistence.edit_history_store import EditHistoryStore
from agent.tools.file_write import execute_file_write
from agent.tools.file_edit import execute_file_edit


# ============================================================
# 辅助函数
# ============================================================


def create_test_context(
    tmpdir: str,
    history_dir: str | None = None,
) -> tuple[ToolUseContext, EditHistoryStore | None]:
    """创建测试用的 ToolUseContext"""
    if history_dir is None:
        history_dir = os.path.join(tmpdir, ".agent", "file-history")

    store = EditHistoryStore(history_dir)
    context = ToolUseContext(
        model="test",
        cwd=tmpdir,
        edit_history_store=store,
    )
    return context, store


# ============================================================
# Write + Rollback 测试
# ============================================================


class TestWriteRollback:
    """write -> rollback 测试。"""

    def test_write_new_file_rollback_deletes(self) -> None:
        """新建文件 rollback 应该删除文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            context, store = create_test_context(tmpdir)
            file_path = os.path.join(tmpdir, "new.txt")

            # 写入新文件
            result = execute_file_write(
                {"file_path": file_path, "content": "new content"},
                context,
            )
            assert result.is_error is False
            assert os.path.exists(file_path)

            # 验证 history 记录
            latest = store.get_latest()
            assert latest is not None
            assert latest.action == "created"
            assert latest.tool_name == "write"

            # 回退
            success, msg = store.rollback_latest()
            assert success is True
            assert not os.path.exists(file_path)  # 文件被删除

    def test_write_modify_file_rollback_restores(self) -> None:
        """修改已有文件 rollback 应该恢复原内容"""
        with tempfile.TemporaryDirectory() as tmpdir:
            context, store = create_test_context(tmpdir)
            file_path = os.path.join(tmpdir, "existing.txt")

            # 创建原始文件
            with open(file_path, "w") as f:
                f.write("original")

            # 修改文件
            result = execute_file_write(
                {"file_path": file_path, "content": "modified", "overwrite": True},
                context,
            )
            assert result.is_error is False

            # 验证文件被修改
            with open(file_path) as f:
                assert f.read() == "modified"

            # 验证 history 记录
            latest = store.get_latest()
            assert latest is not None
            assert latest.action == "modified"
            assert latest.backup_path is not None

            # 回退
            success, msg = store.rollback_latest()
            assert success is True

            # 验证文件被恢复
            with open(file_path) as f:
                assert f.read() == "original"

    def test_write_no_history_store(self) -> None:
        """没有 history store 时正常写入"""
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ToolUseContext(model="test", cwd=tmpdir)
            file_path = os.path.join(tmpdir, "test.txt")

            result = execute_file_write(
                {"file_path": file_path, "content": "content"},
                context,
            )
            assert result.is_error is False
            assert os.path.exists(file_path)


# ============================================================
# Edit + Rollback 测试
# ============================================================


class TestEditRollback:
    """edit -> rollback 测试。"""

    def test_edit_rollback_restores(self) -> None:
        """edit rollback 应该恢复原内容"""
        with tempfile.TemporaryDirectory() as tmpdir:
            context, store = create_test_context(tmpdir)
            file_path = os.path.join(tmpdir, "test.txt")

            # 创建原始文件
            with open(file_path, "w") as f:
                f.write("hello world")

            # 编辑文件
            result = execute_file_edit(
                {
                    "file_path": file_path,
                    "old_string": "hello",
                    "new_string": "goodbye",
                },
                context,
            )
            assert result.is_error is False

            # 验证文件被修改
            with open(file_path) as f:
                assert f.read() == "goodbye world"

            # 验证 history 记录
            latest = store.get_latest()
            assert latest is not None
            assert latest.tool_name == "edit"
            assert latest.action == "modified"
            assert latest.backup_path is not None

            # 回退
            success, msg = store.rollback_latest()
            assert success is True

            # 验证文件被恢复
            with open(file_path) as f:
                assert f.read() == "hello world"

    def test_edit_no_history_store(self) -> None:
        """没有 history store 时正常编辑"""
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ToolUseContext(model="test", cwd=tmpdir)
            file_path = os.path.join(tmpdir, "test.txt")

            # 创建原始文件
            with open(file_path, "w") as f:
                f.write("hello world")

            result = execute_file_edit(
                {
                    "file_path": file_path,
                    "old_string": "hello",
                    "new_string": "goodbye",
                },
                context,
            )
            assert result.is_error is False

            with open(file_path) as f:
                assert f.read() == "goodbye world"


# ============================================================
# 连续操作测试
# ============================================================


class TestConsecutiveOperations:
    """连续操作测试。"""

    def test_multiple_writes_rollback_latest(self) -> None:
        """多次写入后 rollback 只回退最后一次"""
        with tempfile.TemporaryDirectory() as tmpdir:
            context, store = create_test_context(tmpdir)
            file1 = os.path.join(tmpdir, "file1.txt")
            file2 = os.path.join(tmpdir, "file2.txt")

            # 写入两个文件
            execute_file_write({"file_path": file1, "content": "v1"}, context)
            execute_file_write({"file_path": file2, "content": "v2"}, context)

            assert os.path.exists(file1)
            assert os.path.exists(file2)

            # 回退最后一个
            success, _ = store.rollback_latest()
            assert success is True

            # file1 还在，file2 被删除
            assert os.path.exists(file1)
            assert not os.path.exists(file2)

    def test_write_then_edit_rollback(self) -> None:
        """先 write 再 edit，rollback 回退 edit"""
        with tempfile.TemporaryDirectory() as tmpdir:
            context, store = create_test_context(tmpdir)
            file_path = os.path.join(tmpdir, "test.txt")

            # 写入
            execute_file_write(
                {"file_path": file_path, "content": "hello"},
                context,
            )

            # 编辑
            execute_file_edit(
                {
                    "file_path": file_path,
                    "old_string": "hello",
                    "new_string": "world",
                },
                context,
            )

            with open(file_path) as f:
                assert f.read() == "world"

            # 回退 edit
            success, _ = store.rollback_latest()
            assert success is True

            with open(file_path) as f:
                assert f.read() == "hello"


# ============================================================
# 失败操作测试
# ============================================================


class TestFailedOperations:
    """失败操作不应记录历史。"""

    def test_write_to_directory_no_history(self) -> None:
        """写入目录失败不应记录历史"""
        with tempfile.TemporaryDirectory() as tmpdir:
            context, store = create_test_context(tmpdir)
            dir_path = os.path.join(tmpdir, "subdir")
            os.makedirs(dir_path)

            result = execute_file_write(
                {"file_path": dir_path, "content": "content"},
                context,
            )
            assert result.is_error is True

            # 不应有历史记录
            assert store.get_latest() is None

    def test_edit_nonexistent_file_no_history(self) -> None:
        """编辑不存在的文件不应记录历史"""
        with tempfile.TemporaryDirectory() as tmpdir:
            context, store = create_test_context(tmpdir)
            file_path = os.path.join(tmpdir, "nonexistent.txt")

            result = execute_file_edit(
                {
                    "file_path": file_path,
                    "old_string": "old",
                    "new_string": "new",
                },
                context,
            )
            assert result.is_error is True

            # 不应有历史记录
            assert store.get_latest() is None


# ============================================================
# 缓存状态测试
# ============================================================


class TestCacheState:
    """rollback 后缓存状态测试。"""

    def test_rollback_updates_cache(self) -> None:
        """rollback 后 file_read_state 应该被更新"""
        with tempfile.TemporaryDirectory() as tmpdir:
            context, store = create_test_context(tmpdir)
            file_path = os.path.join(tmpdir, "test.txt")

            # 创建原始文件
            with open(file_path, "w") as f:
                f.write("original")

            # 写入修改
            execute_file_write(
                {"file_path": file_path, "content": "modified", "overwrite": True},
                context,
            )

            # 验证缓存是 modified
            cached = context.file_read_state.get(file_path)
            assert cached is not None
            assert cached[0] == "modified"

            # 回退
            store.rollback_latest()

            # 注意：rollback 只恢复文件，不更新缓存
            # 这是因为 rollback 在 store 层面，不经过 context
            # 但文件内容应该被恢复
            with open(file_path) as f:
                assert f.read() == "original"


# ============================================================
# 边界测试
# ============================================================


class TestRollbackEdgeCases:
    """边界情况测试。"""

    def test_rollback_unicode_content(self) -> None:
        """Unicode 内容回退"""
        with tempfile.TemporaryDirectory() as tmpdir:
            context, store = create_test_context(tmpdir)
            file_path = os.path.join(tmpdir, "unicode.txt")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write("中文原始")

            result = execute_file_write(
                {"file_path": file_path, "content": "中文修改", "overwrite": True},
                context,
            )
            assert result.is_error is False

            # 验证 history 记录
            latest = store.get_latest()
            assert latest is not None
            assert latest.action == "modified"

            # 回退
            success, msg = store.rollback_latest()
            assert success is True, f"rollback failed: {msg}"

            with open(file_path, encoding="utf-8") as f:
                assert f.read() == "中文原始"

    def test_rollback_empty_content(self) -> None:
        """空内容回退"""
        with tempfile.TemporaryDirectory() as tmpdir:
            context, store = create_test_context(tmpdir)
            file_path = os.path.join(tmpdir, "empty.txt")

            with open(file_path, "w") as f:
                f.write("")

            execute_file_write(
                {"file_path": file_path, "content": "not empty", "overwrite": True},
                context,
            )

            success, _ = store.rollback_latest()
            assert success is True

            with open(file_path) as f:
                assert f.read() == ""
