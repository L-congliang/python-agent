"""Session Policy 测试

验证 session 级权限策略的记录、查询和清空功能。
"""

from __future__ import annotations

import os
import tempfile

import pytest

from agent.permissions.session_policy import (
    SessionPermissionPolicy,
    normalize_bash_command,
    normalize_file_path,
    extract_permission_key,
)


# ============================================================
# SessionPermissionPolicy 测试
# ============================================================


class TestSessionPermissionPolicy:
    """SessionPermissionPolicy 核心功能测试。"""

    def test_initial_state(self) -> None:
        """初始状态：没有任何 allow"""
        policy = SessionPermissionPolicy()
        assert policy.is_allowed("bash", "ls -la") is False
        assert policy.get_allowed_count() == 0

    def test_remember_allow_session(self) -> None:
        """记住 session allow"""
        policy = SessionPermissionPolicy()
        policy.remember_allow("bash", "ls -la", scope="session")

        assert policy.is_allowed("bash", "ls -la") is True
        assert policy.get_allowed_count() == 1

    def test_remember_allow_once_not_stored(self) -> None:
        """allow-once 不写入 session store"""
        policy = SessionPermissionPolicy()
        policy.remember_allow("bash", "ls -la", scope="once")

        # allow-once 不应该被 is_allowed 命中
        assert policy.is_allowed("bash", "ls -la") is False
        assert policy.get_allowed_count() == 0

    def test_different_commands_not_matched(self) -> None:
        """不同命令不能误命中"""
        policy = SessionPermissionPolicy()
        policy.remember_allow("bash", "ls -la", scope="session")

        assert policy.is_allowed("bash", "ls -la") is True
        assert policy.is_allowed("bash", "rm -rf /") is False
        assert policy.is_allowed("bash", "ls") is False

    def test_different_tools_not_matched(self) -> None:
        """不同工具不能误命中"""
        policy = SessionPermissionPolicy()
        policy.remember_allow("bash", "ls -la", scope="session")

        assert policy.is_allowed("bash", "ls -la") is True
        assert policy.is_allowed("write", "ls -la") is False

    def test_write_edit_path_matching(self) -> None:
        """write/edit 按路径匹配"""
        policy = SessionPermissionPolicy()
        policy.remember_allow("write", "/tmp/test.txt", scope="session")

        assert policy.is_allowed("write", "/tmp/test.txt") is True
        assert policy.is_allowed("write", "/tmp/other.txt") is False
        assert policy.is_allowed("edit", "/tmp/test.txt") is False

    def test_clear(self) -> None:
        """清空 session policy"""
        policy = SessionPermissionPolicy()
        policy.remember_allow("bash", "ls -la", scope="session")
        policy.remember_allow("write", "/tmp/test.txt", scope="session")

        assert policy.get_allowed_count() == 2

        policy.clear()

        assert policy.is_allowed("bash", "ls -la") is False
        assert policy.is_allowed("write", "/tmp/test.txt") is False
        assert policy.get_allowed_count() == 0

    def test_multiple_allows(self) -> None:
        """多个 allow 记录"""
        policy = SessionPermissionPolicy()
        policy.remember_allow("bash", "ls -la", scope="session")
        policy.remember_allow("bash", "pwd", scope="session")
        policy.remember_allow("write", "/tmp/a.txt", scope="session")

        assert policy.get_allowed_count() == 3
        assert policy.is_allowed("bash", "ls -la") is True
        assert policy.is_allowed("bash", "pwd") is True
        assert policy.is_allowed("write", "/tmp/a.txt") is True

    def test_overwrite_session_allow(self) -> None:
        """重复 session allow 覆盖"""
        policy = SessionPermissionPolicy()
        policy.remember_allow("bash", "ls -la", scope="session")
        policy.remember_allow("bash", "ls -la", scope="session")

        # 应该只有一条记录
        assert policy.get_allowed_count() == 1


# ============================================================
# normalize 函数测试
# ============================================================


class TestNormalizeFunctions:
    """normalize 函数测试。"""

    def test_normalize_bash_command(self) -> None:
        """规范化 bash 命令"""
        assert normalize_bash_command("  ls -la  ") == "ls -la"
        assert normalize_bash_command("ls -la") == "ls -la"
        assert normalize_bash_command("") == ""

    def test_normalize_file_path_absolute(self) -> None:
        """规范化绝对路径"""
        assert normalize_file_path("/tmp/test.txt") == os.path.normpath("/tmp/test.txt")
        assert normalize_file_path("/tmp/../tmp/test.txt") == os.path.normpath("/tmp/test.txt")

    def test_normalize_file_path_relative(self) -> None:
        """规范化相对路径"""
        result = normalize_file_path("test.txt", "/workspace")
        assert os.path.isabs(result)
        assert result.endswith("test.txt")

    def test_normalize_file_path_with_cwd(self) -> None:
        """使用 cwd 规范化路径"""
        result = normalize_file_path("src/main.py", "/workspace")
        expected = os.path.normpath(os.path.abspath(os.path.join("/workspace", "src/main.py")))
        assert result == expected


# ============================================================
# extract_permission_key 测试
# ============================================================


class TestExtractPermissionKey:
    """extract_permission_key 测试。"""

    def test_bash_command(self) -> None:
        """bash 命令提取 key"""
        key = extract_permission_key("bash", {"command": "ls -la"})
        assert key == "ls -la"

    def test_bash_command_with_spaces(self) -> None:
        """bash 命令带空格"""
        key = extract_permission_key("bash", {"command": "  ls -la  "})
        assert key == "ls -la"

    def test_write_file_path(self) -> None:
        """write 文件路径提取 key"""
        key = extract_permission_key("write", {"file_path": "/tmp/test.txt"})
        assert key == os.path.normpath("/tmp/test.txt")

    def test_edit_file_path(self) -> None:
        """edit 文件路径提取 key"""
        key = extract_permission_key("edit", {"file_path": "/tmp/test.txt"})
        assert key == os.path.normpath("/tmp/test.txt")

    def test_unsupported_tool(self) -> None:
        """不支持的工具返回 None"""
        key = extract_permission_key("read", {"file_path": "/tmp/test.txt"})
        assert key is None

    def test_bash_empty_command(self) -> None:
        """空命令"""
        key = extract_permission_key("bash", {})
        assert key == ""

    def test_write_empty_path(self) -> None:
        """空路径"""
        key = extract_permission_key("write", {})
        assert key is None


# ============================================================
# 边界测试
# ============================================================


class TestSessionPolicyEdgeCases:
    """边界情况测试。"""

    def test_unicode_command(self) -> None:
        """Unicode 命令"""
        policy = SessionPermissionPolicy()
        policy.remember_allow("bash", "echo '中文'", scope="session")

        assert policy.is_allowed("bash", "echo '中文'") is True

    def test_special_characters_in_path(self) -> None:
        """路径包含特殊字符"""
        policy = SessionPermissionPolicy()
        policy.remember_allow("write", "/tmp/dir with spaces/file (1).txt", scope="session")

        assert policy.is_allowed("write", "/tmp/dir with spaces/file (1).txt") is True

    def test_long_command(self) -> None:
        """长命令"""
        policy = SessionPermissionPolicy()
        long_command = "ls " + " ".join([f"dir{i}" for i in range(100)])
        policy.remember_allow("bash", long_command, scope="session")

        assert policy.is_allowed("bash", long_command) is True
