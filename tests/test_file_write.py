"""测试文件写入工具"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

import pytest

from agent.core.context import ToolUseContext, AbortController, FileReadState
from agent.core.types import ToolResult
from agent.tools.file_write import (
    _resolve_path,
    _ensure_directory,
    _check_write_permission,
    _check_disk_space,
    _update_cache,
    _validate_notebook_structure,
    _write_notebook,
    FILE_WRITE_PARAMETERS,
    validate_file_write_input,
    execute_file_write,
    file_write_tool,
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
# 辅助函数测试
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


# ============================================================
# Notebook 写入测试
# ============================================================


class TestValidateNotebookStructure:
    """Notebook 结构验证测试"""

    def test_valid_notebook(self):
        """有效的 Notebook 结构"""
        notebook = {
            "cells": [
                {"cell_type": "code", "source": ["print('hello')"], "outputs": []}
            ],
            "metadata": {},
            "nbformat": 4,
        }
        assert _validate_notebook_structure(notebook) is None

    def test_missing_cells_field(self):
        """缺少 cells 字段"""
        notebook = {"metadata": {}, "nbformat": 4}
        result = _validate_notebook_structure(notebook)
        assert result is not None
        assert "cells" in result

    def test_missing_metadata_field(self):
        """缺少 metadata 字段"""
        notebook = {"cells": [], "nbformat": 4}
        result = _validate_notebook_structure(notebook)
        assert result is not None
        assert "metadata" in result

    def test_missing_nbformat_field(self):
        """缺少 nbformat 字段"""
        notebook = {"cells": [], "metadata": {}}
        result = _validate_notebook_structure(notebook)
        assert result is not None
        assert "nbformat" in result

    def test_cells_not_list(self):
        """cells 字段不是列表"""
        notebook = {"cells": "not a list", "metadata": {}, "nbformat": 4}
        result = _validate_notebook_structure(notebook)
        assert result is not None
        assert "列表" in result

    def test_cell_missing_cell_type(self):
        """cell 缺少 cell_type 字段"""
        notebook = {
            "cells": [{"source": ["print('hello')"]}],
            "metadata": {},
            "nbformat": 4,
        }
        result = _validate_notebook_structure(notebook)
        assert result is not None
        assert "cell_type" in result

    def test_cell_missing_source(self):
        """cell 缺少 source 字段"""
        notebook = {
            "cells": [{"cell_type": "code"}],
            "metadata": {},
            "nbformat": 4,
        }
        result = _validate_notebook_structure(notebook)
        assert result is not None
        assert "source" in result

    def test_empty_cells_list(self):
        """空 cells 列表是有效的"""
        notebook = {"cells": [], "metadata": {}, "nbformat": 4}
        assert _validate_notebook_structure(notebook) is None


class TestWriteNotebook:
    """Notebook 写入测试"""

    def test_valid_notebook_write(self, tmp_dir):
        """写入有效的 Notebook"""
        notebook = {
            "cells": [
                {"cell_type": "code", "source": ["print('hello')"], "outputs": []}
            ],
            "metadata": {},
            "nbformat": 4,
        }
        file_path = str(tmp_dir / "test.ipynb")
        _write_notebook(file_path, json.dumps(notebook))

        with open(file_path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert len(loaded["cells"]) == 1
        assert loaded["nbformat"] == 4

    def test_invalid_json_raises_error(self, tmp_dir):
        """无效 JSON 格式抛出 ValueError"""
        file_path = str(tmp_dir / "test.ipynb")
        with pytest.raises(ValueError, match="无效的 JSON"):
            _write_notebook(file_path, "{invalid json}")

    def test_invalid_structure_raises_error(self, tmp_dir):
        """无效 Notebook 结构抛出 ValueError"""
        file_path = str(tmp_dir / "test.ipynb")
        with pytest.raises(ValueError, match="Notebook 缺少"):
            _write_notebook(file_path, json.dumps({"cells": []}))

    def test_utf8_encoding(self, tmp_dir):
        """中文内容正确写入"""
        notebook = {
            "cells": [
                {"cell_type": "code", "source": ["print('你好世界')"], "outputs": []}
            ],
            "metadata": {},
            "nbformat": 4,
        }
        file_path = str(tmp_dir / "test.ipynb")
        _write_notebook(file_path, json.dumps(notebook))

        with open(file_path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert "你好世界" in loaded["cells"][0]["source"][0]


# ============================================================
# 输入校验测试
# ============================================================


class TestValidateFileWriteInput:
    """输入校验测试"""

    def test_valid_input(self, context, tmp_dir):
        """有效输入校验通过"""
        result = validate_file_write_input(
            {"file_path": "test.txt", "content": "hello"}, context
        )
        assert result.is_valid

    def test_empty_path(self, context):
        """空路径校验失败"""
        result = validate_file_write_input(
            {"file_path": "", "content": "hello"}, context
        )
        assert not result.is_valid
        assert "file_path" in result.message

    def test_none_path(self, context):
        """None 路径校验失败"""
        result = validate_file_write_input(
            {"file_path": None, "content": "hello"}, context
        )
        assert not result.is_valid

    def test_whitespace_only_path(self, context):
        """纯空格路径校验失败"""
        result = validate_file_write_input(
            {"file_path": "   ", "content": "hello"}, context
        )
        assert not result.is_valid

    def test_non_string_path(self, context):
        """非字符串路径校验失败"""
        result = validate_file_write_input(
            {"file_path": 123, "content": "hello"}, context
        )
        assert not result.is_valid

    def test_none_content(self, context):
        """None 内容校验失败"""
        result = validate_file_write_input(
            {"file_path": "test.txt", "content": None}, context
        )
        assert not result.is_valid
        assert "content" in result.message

    def test_non_string_content(self, context):
        """非字符串内容校验失败"""
        result = validate_file_write_input(
            {"file_path": "test.txt", "content": 123}, context
        )
        assert not result.is_valid

    def test_empty_content_valid(self, context):
        """空字符串内容是有效的（创建空文件）"""
        result = validate_file_write_input(
            {"file_path": "test.txt", "content": ""}, context
        )
        assert result.is_valid

    def test_path_is_directory(self, context, tmp_dir):
        """路径是目录校验失败"""
        dir_path = tmp_dir / "test_dir"
        dir_path.mkdir()
        result = validate_file_write_input(
            {"file_path": "test_dir", "content": "hello"}, context
        )
        assert not result.is_valid
        assert "目录" in result.message


# ============================================================
# Write 工具执行测试
# ============================================================


class TestExecuteFileWrite:
    """Write 工具执行测试"""

    def test_basic_write(self, context, tmp_dir):
        """创建新文件"""
        result = execute_file_write(
            {"file_path": "test.txt", "content": "hello world"}, context
        )
        assert not result.is_error
        assert "写入成功" in result.output
        # 验证文件内容
        file_path = tmp_dir / "test.txt"
        assert file_path.exists()
        assert file_path.read_text(encoding="utf-8") == "hello world"

    def test_overwrite_existing(self, context, tmp_dir):
        """现有文件默认拒绝覆盖"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("old content", encoding="utf-8")
        result = execute_file_write(
            {"file_path": "test.txt", "content": "new content"}, context
        )
        assert result.is_error
        assert "默认不会覆盖" in result.output
        assert "overwrite=true" in result.output
        assert file_path.read_text(encoding="utf-8") == "old content"

    def test_overwrite_existing_with_explicit_flag(self, context, tmp_dir):
        """显式 overwrite=true 时允许覆盖"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("old content", encoding="utf-8")
        result = execute_file_write(
            {"file_path": "test.txt", "content": "new content", "overwrite": True},
            context,
        )
        assert not result.is_error
        assert "覆盖写入成功" in result.output
        assert file_path.read_text(encoding="utf-8") == "new content"

    def test_auto_create_directory(self, context, tmp_dir):
        """自动创建父目录"""
        result = execute_file_write(
            {"file_path": "src/utils/helper.py", "content": "print('hello')"},
            context,
        )
        assert not result.is_error
        file_path = tmp_dir / "src" / "utils" / "helper.py"
        assert file_path.exists()

    def test_path_is_directory(self, context, tmp_dir):
        """路径是目录返回错误"""
        dir_path = tmp_dir / "test_dir"
        dir_path.mkdir()
        result = execute_file_write(
            {"file_path": "test_dir", "content": "hello"}, context
        )
        assert result.is_error
        assert "目录" in result.output

    def test_notebook_write(self, context, tmp_dir):
        """写入 Jupyter Notebook"""
        notebook = {
            "cells": [
                {"cell_type": "code", "source": ["print('hello')"], "outputs": []}
            ],
            "metadata": {},
            "nbformat": 4,
        }
        result = execute_file_write(
            {"file_path": "test.ipynb", "content": json.dumps(notebook)}, context
        )
        assert not result.is_error
        file_path = tmp_dir / "test.ipynb"
        with open(file_path, encoding="utf-8") as f:
            loaded = json.load(f)
            assert len(loaded["cells"]) == 1

    def test_write_abort(self, context, tmp_dir):
        """中断文件写入"""
        context.abort_controller.abort()
        result = execute_file_write(
            {"file_path": "test.txt", "content": "hello"}, context
        )
        assert result.is_error
        assert "取消" in result.output

    def test_write_cache_update(self, context, tmp_dir):
        """写入后更新缓存"""
        result = execute_file_write(
            {"file_path": "test.txt", "content": "hello"}, context
        )
        assert not result.is_error
        abs_path = str(tmp_dir / "test.txt")
        cached = context.file_read_state.get(abs_path)
        assert cached is not None
        assert cached[0] == "hello"

    def test_utf8_content(self, context, tmp_dir):
        """UTF-8 中文内容正确写入"""
        result = execute_file_write(
            {"file_path": "test.txt", "content": "你好世界"}, context
        )
        assert not result.is_error
        file_path = tmp_dir / "test.txt"
        assert file_path.read_text(encoding="utf-8") == "你好世界"

    def test_empty_content(self, context, tmp_dir):
        """空内容创建空文件"""
        result = execute_file_write(
            {"file_path": "test.txt", "content": ""}, context
        )
        assert not result.is_error
        file_path = tmp_dir / "test.txt"
        assert file_path.read_text(encoding="utf-8") == ""

    def test_invalid_notebook_returns_error(self, context, tmp_dir):
        """无效 Notebook 内容返回错误"""
        result = execute_file_write(
            {"file_path": "test.ipynb", "content": "{invalid json}"}, context
        )
        assert result.is_error
        assert "输入错误" in result.output


# ============================================================
# 工具属性测试
# ============================================================


class TestFileWriteTool:
    """Write 工具属性测试"""

    def test_tool_name(self):
        """工具名称正确"""
        assert file_write_tool.name == "write"

    def test_tool_description(self):
        """工具描述包含写入关键词"""
        assert "写入" in file_write_tool.description

    def test_tool_parameters(self):
        """工具参数定义正确"""
        assert "file_path" in file_write_tool.parameters["properties"]
        assert "content" in file_write_tool.parameters["properties"]
        assert "overwrite" in file_write_tool.parameters["properties"]
        assert "file_path" in file_write_tool.parameters["required"]
        assert "content" in file_write_tool.parameters["required"]

    def test_not_read_only(self):
        """Write 工具不是只读的"""
        assert not file_write_tool.is_read_only({})

    def test_not_concurrency_safe(self):
        """Write 工具不支持并发"""
        assert not file_write_tool.is_concurrency_safe({})

    def test_is_enabled(self):
        """Write 工具默认启用"""
        assert file_write_tool.is_enabled()

    def test_is_not_destructive(self):
        """Write 工具默认非破坏性"""
        assert not file_write_tool.is_destructive({})

    def test_overwrite_is_destructive(self):
        """显式覆盖应视为破坏性操作"""
        assert file_write_tool.is_destructive({"overwrite": True})

    def test_get_summary(self):
        """获取摘要"""
        summary = file_write_tool.get_summary({"file_path": "test.txt"})
        assert summary is not None
        assert "test.txt" in summary

    def test_get_user_facing_name(self):
        """获取用户可见名称"""
        name = file_write_tool.get_user_facing_name({})
        assert name == "Write"

    def test_get_activity_description(self):
        """获取活动描述"""
        desc = file_write_tool.get_activity_description({"file_path": "test.txt"})
        assert desc is not None
        assert "test.txt" in desc


# ============================================================
# FILE_WRITE_PARAMETERS 测试
# ============================================================


class TestFileWriteParameters:
    """参数定义测试"""

    def test_type_is_object(self):
        """类型是 object"""
        assert FILE_WRITE_PARAMETERS["type"] == "object"

    def test_has_required_fields(self):
        """必填字段定义正确"""
        assert "file_path" in FILE_WRITE_PARAMETERS["required"]
        assert "content" in FILE_WRITE_PARAMETERS["required"]

    def test_properties_types(self):
        """属性类型定义正确"""
        props = FILE_WRITE_PARAMETERS["properties"]
        assert props["file_path"]["type"] == "string"
        assert props["content"]["type"] == "string"
