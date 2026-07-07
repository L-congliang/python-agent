"""Edit History Store 测试

验证编辑历史的记录、查询和回退功能。
"""

from __future__ import annotations

import os
import tempfile

import pytest

from agent.persistence.edit_history_store import EditHistoryStore, EditHistoryRecord


# ============================================================
# 辅助函数
# ============================================================


def create_temp_store() -> tuple[EditHistoryStore, str]:
    """创建临时目录的 store，返回 (store, tmpdir)"""
    tmpdir = tempfile.mkdtemp()
    store = EditHistoryStore(os.path.join(tmpdir, ".agent", "file-history"))
    return store, tmpdir


# ============================================================
# record_write 测试
# ============================================================


class TestRecordWrite:
    """record_write 方法测试。"""

    def test_record_new_file(self) -> None:
        """新建文件记录为 created"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "new.txt")

        record = store.record_write(file_path, "hello", is_new=True)

        assert record.tool_name == "write"
        assert record.file_path == os.path.abspath(file_path)
        assert record.action == "created"
        assert record.backup_path is None  # 新建文件没有备份
        assert record.before_hash == ""  # 新建文件没有 before
        assert record.after_hash != ""
        assert record.record_id != ""

    def test_record_modify_file(self) -> None:
        """修改已有文件记录为 modified"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "existing.txt")

        # 先创建文件
        with open(file_path, "w") as f:
            f.write("old content")

        record = store.record_write(file_path, "new content", is_new=False)

        assert record.tool_name == "write"
        assert record.action == "modified"
        assert record.backup_path is not None  # 修改文件有备份
        assert record.before_hash != ""
        assert record.after_hash != ""
        assert os.path.exists(record.backup_path)

    def test_record_with_preview(self) -> None:
        """记录包含 preview"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "test.txt")

        record = store.record_write(file_path, "content", is_new=True, preview="写入测试")

        assert record.preview == "写入测试"


# ============================================================
# record_edit 测试
# ============================================================


class TestRecordEdit:
    """record_edit 方法测试。"""

    def test_record_edit(self) -> None:
        """记录 edit 操作"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "test.txt")

        # 先创建文件
        with open(file_path, "w") as f:
            f.write("old content")

        record = store.record_edit(file_path, "old content", "new content", "diff preview")

        assert record.tool_name == "edit"
        assert record.action == "modified"
        assert record.backup_path is not None
        assert record.before_hash != ""
        assert record.after_hash != ""
        assert record.preview == "diff preview"


# ============================================================
# record_rollback 测试
# ============================================================


class TestRecordRollback:
    """record_rollback 方法测试。"""

    def test_record_rollback(self) -> None:
        """记录 rollback 操作"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "test.txt")

        record = store.record_rollback(file_path, "deleted", "已删除")

        assert record.tool_name == "rollback"
        assert record.action == "deleted"
        assert record.preview == "已删除"


# ============================================================
# get_latest 测试
# ============================================================


class TestGetLatest:
    """get_latest 方法测试。"""

    def test_no_records(self) -> None:
        """没有记录时返回 None"""
        store, _ = create_temp_store()
        assert store.get_latest() is None

    def test_get_latest_write(self) -> None:
        """获取最近的 write 记录"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "test.txt")

        store.record_write(file_path, "v1", is_new=True)
        store.record_write(file_path, "v2", is_new=False)

        latest = store.get_latest()
        assert latest is not None
        assert latest.after_hash == store._compute_hash("v2")

    def test_get_latest_skips_rollback(self) -> None:
        """get_latest 跳过 rollback 记录"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "test.txt")

        store.record_write(file_path, "v1", is_new=True)
        store.record_rollback(file_path, "deleted")

        latest = store.get_latest()
        assert latest is not None
        assert latest.tool_name == "write"

    def test_get_latest_edit(self) -> None:
        """获取最近的 edit 记录"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "test.txt")

        # 先创建文件
        with open(file_path, "w") as f:
            f.write("v1")

        store.record_write(file_path, "v1", is_new=True)
        store.record_edit(file_path, "v1", "v2")

        latest = store.get_latest()
        assert latest is not None
        assert latest.tool_name == "edit"


# ============================================================
# get_all 测试
# ============================================================


class TestGetAll:
    """get_all 方法测试。"""

    def test_get_all_empty(self) -> None:
        """没有记录时返回空列表"""
        store, _ = create_temp_store()
        assert store.get_all() == []

    def test_get_all_ordered(self) -> None:
        """记录按时间顺序返回"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "test.txt")

        # 先创建文件
        with open(file_path, "w") as f:
            f.write("v1")

        store.record_write(file_path, "v1", is_new=True)
        store.record_write(file_path, "v2", is_new=False)

        # 更新文件内容以便 record_edit 能创建备份
        with open(file_path, "w") as f:
            f.write("v2")

        store.record_edit(file_path, "v2", "v3")

        records = store.get_all()
        assert len(records) == 3
        assert records[0].tool_name == "write"
        assert records[1].tool_name == "write"
        assert records[2].tool_name == "edit"


# ============================================================
# get_by_file 测试
# ============================================================


class TestGetByFile:
    """get_by_file 方法测试。"""

    def test_get_by_file(self) -> None:
        """获取指定文件的记录"""
        store, tmpdir = create_temp_store()
        file1 = os.path.join(tmpdir, "file1.txt")
        file2 = os.path.join(tmpdir, "file2.txt")

        store.record_write(file1, "a", is_new=True)
        store.record_write(file2, "b", is_new=True)
        store.record_write(file1, "c", is_new=False)

        records = store.get_by_file(file1)
        assert len(records) == 2
        assert all(r.file_path == os.path.abspath(file1) for r in records)


# ============================================================
# rollback_latest 测试
# ============================================================


class TestRollbackLatest:
    """rollback_latest 方法测试。"""

    def test_rollback_no_history(self) -> None:
        """没有历史记录时返回失败"""
        store, _ = create_temp_store()
        success, msg = store.rollback_latest()
        assert success is False
        assert "没有可回退" in msg

    def test_rollback_created_file(self) -> None:
        """回退新建文件（删除文件）"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "new.txt")

        # 创建文件并记录
        with open(file_path, "w") as f:
            f.write("new file content")
        store.record_write(file_path, "new file content", is_new=True)

        # 确认文件存在
        assert os.path.exists(file_path)

        # 回退
        success, msg = store.rollback_latest()

        assert success is True
        assert "已回退" in msg
        assert not os.path.exists(file_path)  # 文件被删除

        # 验证 rollback 记录被写入
        records = store.get_all()
        assert any(r.tool_name == "rollback" for r in records)

    def test_rollback_modified_file(self) -> None:
        """回退修改文件（恢复备份）"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "existing.txt")

        # 创建原始文件
        with open(file_path, "w") as f:
            f.write("original content")

        # 记录修改（此时会创建备份）
        store.record_write(file_path, "modified content", is_new=False)

        # 实际修改文件
        with open(file_path, "w") as f:
            f.write("modified content")

        # 确认文件被修改
        with open(file_path) as f:
            assert f.read() == "modified content"

        # 回退
        success, msg = store.rollback_latest()

        assert success is True
        assert "已回退" in msg

        # 验证文件被恢复
        with open(file_path) as f:
            assert f.read() == "original content"

    def test_rollback_created_file_already_deleted(self) -> None:
        """回退新建文件，但文件已不存在"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "new.txt")

        # 记录创建（不实际创建文件）
        store.record_write(file_path, "content", is_new=True)

        # 回退
        success, msg = store.rollback_latest()

        assert success is True
        assert "已不存在" in msg

    def test_rollback_edit(self) -> None:
        """回退 edit 操作"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "test.txt")

        # 创建原始文件
        with open(file_path, "w") as f:
            f.write("original")

        # 记录 edit
        store.record_edit(file_path, "original", "modified")

        # 修改文件
        with open(file_path, "w") as f:
            f.write("modified")

        # 回退
        success, msg = store.rollback_latest()

        assert success is True
        with open(file_path) as f:
            assert f.read() == "original"

    def test_rollback_preserves_other_files(self) -> None:
        """回退不影响其他文件"""
        store, tmpdir = create_temp_store()
        file1 = os.path.join(tmpdir, "file1.txt")
        file2 = os.path.join(tmpdir, "file2.txt")

        # 创建两个文件
        with open(file1, "w") as f:
            f.write("content1")
        with open(file2, "w") as f:
            f.write("content2")

        store.record_write(file1, "content1", is_new=True)
        store.record_write(file2, "content2", is_new=True)

        # 回退最后一个
        success, _ = store.rollback_latest()
        assert success is True

        # file1 应该还在
        assert os.path.exists(file1)
        # file2 应该被删除
        assert not os.path.exists(file2)


# ============================================================
# 持久化测试
# ============================================================


class TestPersistence:
    """持久化测试。"""

    def test_records_persist_across_instances(self) -> None:
        """记录在不同实例间持久化"""
        tmpdir = tempfile.mkdtemp()
        history_dir = os.path.join(tmpdir, ".agent", "file-history")

        # 第一个实例写入
        store1 = EditHistoryStore(history_dir)
        file_path = os.path.join(tmpdir, "test.txt")
        store1.record_write(file_path, "content", is_new=True)

        # 第二个实例读取
        store2 = EditHistoryStore(history_dir)
        records = store2.get_all()
        assert len(records) == 1
        assert records[0].tool_name == "write"

    def test_backups_persist(self) -> None:
        """备份文件持久化"""
        tmpdir = tempfile.mkdtemp()
        history_dir = os.path.join(tmpdir, ".agent", "file-history")
        file_path = os.path.join(tmpdir, "test.txt")

        # 创建文件
        with open(file_path, "w") as f:
            f.write("original")

        # 记录修改
        store = EditHistoryStore(history_dir)
        record = store.record_write(file_path, "modified", is_new=False)

        # 验证备份文件存在
        assert record.backup_path is not None
        assert os.path.exists(record.backup_path)

        # 验证备份内容
        with open(record.backup_path) as f:
            assert f.read() == "original"


# ============================================================
# 边界测试
# ============================================================


class TestEdgeCases:
    """边界情况测试。"""

    def test_unicode_content(self) -> None:
        """Unicode 内容"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "unicode.txt")

        record = store.record_write(file_path, "中文内容", is_new=True)
        assert record.after_hash != ""

    def test_empty_content(self) -> None:
        """空内容"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "empty.txt")

        record = store.record_write(file_path, "", is_new=True)
        assert record.after_hash != ""

    def test_large_content(self) -> None:
        """大文件"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "large.txt")

        large_content = "x" * 1_000_000
        record = store.record_write(file_path, large_content, is_new=True)
        assert record.after_hash != ""

    def test_special_characters_in_path(self) -> None:
        """路径包含特殊字符"""
        store, tmpdir = create_temp_store()
        file_path = os.path.join(tmpdir, "dir with spaces", "file (1).txt")

        record = store.record_write(file_path, "content", is_new=True)
        assert record.file_path == os.path.abspath(file_path)
