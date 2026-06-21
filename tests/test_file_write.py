"""测试文件写入工具"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

import pytest

from agent.core.context import ToolUseContext, AbortController, FileReadState
from agent.tools.file_write import (
    _resolve_path,
    _ensure_directory,
    _check_write_permission,
    _check_disk_space,
    _update_cache,
)


@pytest.fixture
def tmp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def context(tmp_dir):
    """创建测试用的 ToolUseContext"""
    return ToolUseContext(
        model="test",
        cwd=str(tmp_dir),
        abort_controller=AbortController(),
        file_read_state=FileReadState(),
    )


# ============================================================
# _resolve_path 测试
# ============================================================


class TestResolvePath:
    """路径解析测试"""

    def test_absolute_path_unchanged(self):
        """绝对路径直接返回"""
        result = _resolve_path("/tmp/test.py", "/home/user")
        assert result == "/tmp/test.py"

    def test_relative_path_resolved(self):
        """相对路径相对于 cwd 解析"""
        result = _resolve_path("src/main.py", "/home/user/project")
        assert result == os.path.abspath("/home/user/project/src/main.py")

    def test_dot_in_path(self):
        """路径中的 . 被正确处理"""
        result = _resolve_path("./test.py", "/tmp")
        assert result == os.path.abspath("/tmp/test.py")

    def test_dotdot_in_path(self):
        """路径中的 .. 被正确处理"""
        result = _resolve_path("../test.py", "/tmp/subdir")
        assert result == os.path.abspath("/tmp/test.py")

    def test_empty_relative_path(self):
        """空相对路径解析为 cwd 本身"""
        result = _resolve_path("", "/home/user")
        assert result == os.path.abspath("/home/user")


# ============================================================
# _ensure_directory 测试
# ============================================================


class TestEnsureDirectory:
    """目录创建测试"""

    def test_creates_nested_directories(self, tmp_dir):
        """自动创建多层嵌套目录"""
        file_path = str(tmp_dir / "a" / "b" / "c" / "test.txt")
        _ensure_directory(file_path)
        assert os.path.isdir(os.path.dirname(file_path))

    def test_existing_directory_no_error(self, tmp_dir):
        """目录已存在时不报错"""
        file_path = str(tmp_dir / "test.txt")
        _ensure_directory(file_path)
        # 再调用一次，不应报错
        _ensure_directory(file_path)

    def test_root_path_no_op(self):
        """根路径不触发目录创建"""
        # 根路径的 dirname 为空字符串，不应报错
        _ensure_directory("/test.txt")


# ============================================================
# _check_write_permission 测试
# ============================================================


class TestCheckWritePermission:
    """写入权限检查测试"""

    def test_writable_existing_file(self, tmp_dir):
        """可写的已存在文件返回 None"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("content")
        assert _check_write_permission(str(file_path)) is None

    def test_writable_new_file_in_writable_dir(self, tmp_dir):
        """在可写目录中创建新文件返回 None"""
        file_path = tmp_dir / "new_file.txt"
        assert _check_write_permission(str(file_path)) is None

    def test_readonly_file_returns_error(self, tmp_dir):
        """只读文件返回错误信息"""
        file_path = tmp_dir / "readonly.txt"
        file_path.write_text("content")
        # 设置只读权限
        file_path.chmod(stat.S_IRUSR)
        try:
            result = _check_write_permission(str(file_path))
            assert result is not None
            assert "不可写" in result
        finally:
            # 恢复权限以便清理
            file_path.chmod(stat.S_IRUSR | stat.S_IWUSR)


# ============================================================
# _check_disk_space 测试
# ============================================================


class TestCheckDiskSpace:
    """磁盘空间检查测试"""

    def test_small_content_returns_none(self, tmp_dir):
        """小文件写入空间足够返回 None"""
        file_path = str(tmp_dir / "test.txt")
        result = _check_disk_space(file_path, 100)
        assert result is None

    def test_huge_content_returns_error_on_linux(self, tmp_dir):
        """超大内容在 Linux 上返回空间不足错误

        注意: Windows 不支持 statvfs，此测试在 Windows 上会返回 None（跳过检查）
        """
        file_path = str(tmp_dir / "test.txt")
        # 请求 1 YB（远超任何磁盘容量）
        result = _check_disk_space(file_path, 1024 * 1024 * 1024 * 1024 * 1024 * 1024)
        # Windows 上 statvfs 不存在，会跳过检查返回 None
        # Linux 上应该返回错误
        if os.name != "nt":
            assert result is not None
            assert "空间不足" in result


# ============================================================
# _update_cache 测试
# ============================================================


class TestUpdateCache:
    """缓存更新测试"""

    def test_cache_set_and_get(self, tmp_dir, context):
        """写入后缓存可读取"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello")

        abs_path = str(file_path)
        _update_cache(abs_path, "hello", context)

        cached = context.file_read_state.get(abs_path)
        assert cached is not None
        content, mtime = cached
        assert content == "hello"

    def test_cache_mtime_matches(self, tmp_dir, context):
        """缓存的 mtime 与文件实际 mtime 一致"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("content")

        abs_path = str(file_path)
        _update_cache(abs_path, "content", context)

        cached = context.file_read_state.get(abs_path)
        assert cached is not None
        _, cached_mtime = cached
        assert cached_mtime == os.path.getmtime(abs_path)

    def test_cache_overwrite(self, tmp_dir, context):
        """重复写入覆盖旧缓存"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("v1")

        abs_path = str(file_path)
        _update_cache(abs_path, "v1", context)

        file_path.write_text("v2")
        _update_cache(abs_path, "v2", context)

        cached = context.file_read_state.get(abs_path)
        assert cached is not None
        content, _ = cached
        assert content == "v2"
