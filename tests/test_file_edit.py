"""测试文件编辑工具"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from agent.core.context import ToolUseContext, AbortController, FileReadState
from agent.core.types import ToolResult, ValidationResult
from agent.tools.file_edit import (
    FILE_EDIT_PARAMETERS,
    validate_file_edit_input,
    execute_file_edit,
    file_edit_tool,
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
# 参数定义测试
# ============================================================


class TestFileEditParameters:
    """参数定义测试"""

    def test_type_is_object(self):
        """类型是 object"""
        assert FILE_EDIT_PARAMETERS["type"] == "object"

    def test_has_required_fields(self):
        """必填字段定义正确"""
        assert "file_path" in FILE_EDIT_PARAMETERS["required"]
        assert "old_string" in FILE_EDIT_PARAMETERS["required"]
        assert "new_string" in FILE_EDIT_PARAMETERS["required"]

    def test_optional_replace_all(self):
        """replace_all 是可选的"""
        assert "replace_all" not in FILE_EDIT_PARAMETERS["required"]

    def test_properties_types(self):
        """属性类型定义正确"""
        props = FILE_EDIT_PARAMETERS["properties"]
        assert props["file_path"]["type"] == "string"
        assert props["old_string"]["type"] == "string"
        assert props["new_string"]["type"] == "string"
        assert props["replace_all"]["type"] == "boolean"


# ============================================================
# 输入校验测试
# ============================================================


class TestValidateFileEditInput:
    """输入校验测试"""

    def test_valid_input(self, context, tmp_dir):
        """有效输入校验通过"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello world", encoding="utf-8")
        result = validate_file_edit_input(
            {"file_path": "test.txt", "old_string": "hello", "new_string": "hi"},
            context,
        )
        assert result.is_valid

    def test_empty_path(self, context):
        """空路径校验失败"""
        result = validate_file_edit_input(
            {"file_path": "", "old_string": "a", "new_string": "b"}, context
        )
        assert not result.is_valid
        assert "file_path" in result.message

    def test_none_path(self, context):
        """None 路径校验失败"""
        result = validate_file_edit_input(
            {"file_path": None, "old_string": "a", "new_string": "b"}, context
        )
        assert not result.is_valid

    def test_whitespace_only_path(self, context):
        """纯空格路径校验失败"""
        result = validate_file_edit_input(
            {"file_path": "   ", "old_string": "a", "new_string": "b"}, context
        )
        assert not result.is_valid

    def test_non_string_path(self, context):
        """非字符串路径校验失败"""
        result = validate_file_edit_input(
            {"file_path": 123, "old_string": "a", "new_string": "b"}, context
        )
        assert not result.is_valid

    def test_none_old_string(self, context, tmp_dir):
        """None old_string 校验失败"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello", encoding="utf-8")
        result = validate_file_edit_input(
            {"file_path": "test.txt", "old_string": None, "new_string": "b"}, context
        )
        assert not result.is_valid
        assert "old_string" in result.message

    def test_non_string_old_string(self, context, tmp_dir):
        """非字符串 old_string 校验失败"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello", encoding="utf-8")
        result = validate_file_edit_input(
            {"file_path": "test.txt", "old_string": 123, "new_string": "b"}, context
        )
        assert not result.is_valid

    def test_empty_old_string(self, context):
        """空 old_string 校验失败"""
        result = validate_file_edit_input(
            {"file_path": "test.txt", "old_string": "", "new_string": "new"}, context
        )
        assert not result.is_valid
        assert "old_string" in result.message

    def test_none_new_string(self, context, tmp_dir):
        """None new_string 校验失败"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello", encoding="utf-8")
        result = validate_file_edit_input(
            {"file_path": "test.txt", "old_string": "a", "new_string": None}, context
        )
        assert not result.is_valid
        assert "new_string" in result.message

    def test_non_string_new_string(self, context, tmp_dir):
        """非字符串 new_string 校验失败"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello", encoding="utf-8")
        result = validate_file_edit_input(
            {"file_path": "test.txt", "old_string": "a", "new_string": 123}, context
        )
        assert not result.is_valid

    def test_empty_new_string(self, context):
        """空 new_string 校验失败"""
        result = validate_file_edit_input(
            {"file_path": "test.txt", "old_string": "old", "new_string": ""}, context
        )
        assert not result.is_valid
        assert "new_string" in result.message

    def test_file_not_exists(self, context):
        """文件不存在校验失败"""
        result = validate_file_edit_input(
            {"file_path": "nonexistent.txt", "old_string": "a", "new_string": "b"},
            context,
        )
        assert not result.is_valid
        assert "不存在" in result.message

    def test_path_is_directory(self, context, tmp_dir):
        """路径是目录校验失败"""
        dir_path = tmp_dir / "test_dir"
        dir_path.mkdir()
        result = validate_file_edit_input(
            {"file_path": "test_dir", "old_string": "a", "new_string": "b"}, context
        )
        assert not result.is_valid
        assert "目录" in result.message

    def test_old_string_not_in_file(self, context, tmp_dir):
        """old_string 不在文件中校验失败"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello world", encoding="utf-8")
        result = validate_file_edit_input(
            {"file_path": "test.txt", "old_string": "not_exist", "new_string": "b"},
            context,
        )
        assert not result.is_valid
        assert "不存在" in result.message

    def test_multiple_matches_without_replace_all(self, context, tmp_dir):
        """多个匹配且 replace_all=False 校验失败"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello hello world", encoding="utf-8")
        result = validate_file_edit_input(
            {"file_path": "test.txt", "old_string": "hello", "new_string": "hi"},
            context,
        )
        assert not result.is_valid
        assert "多个" in result.message

    def test_multiple_matches_with_replace_all(self, context, tmp_dir):
        """多个匹配且 replace_all=True 校验通过"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello hello world", encoding="utf-8")
        result = validate_file_edit_input(
            {
                "file_path": "test.txt",
                "old_string": "hello",
                "new_string": "hi",
                "replace_all": True,
            },
            context,
        )
        assert result.is_valid


# ============================================================
# 核心执行测试
# ============================================================


class TestExecuteFileEdit:
    """核心执行测试"""

    def test_basic_edit(self, context, tmp_dir):
        """基本替换成功"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello world", encoding="utf-8")
        result = execute_file_edit(
            {"file_path": "test.txt", "old_string": "hello", "new_string": "hi"},
            context,
        )
        assert not result.is_error
        assert "修改成功" in result.output
        assert file_path.read_text(encoding="utf-8") == "hi world"

    def test_replace_all(self, context, tmp_dir):
        """替换所有匹配项"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello hello world", encoding="utf-8")
        result = execute_file_edit(
            {
                "file_path": "test.txt",
                "old_string": "hello",
                "new_string": "hi",
                "replace_all": True,
            },
            context,
        )
        assert not result.is_error
        assert file_path.read_text(encoding="utf-8") == "hi hi world"

    def test_replace_single_occurrence(self, context, tmp_dir):
        """默认只替换第一个匹配项"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello hello world", encoding="utf-8")
        result = execute_file_edit(
            {
                "file_path": "test.txt",
                "old_string": "hello",
                "new_string": "hi",
                "replace_all": False,
            },
            context,
        )
        # 因为有多个匹配且 replace_all=False，应该报错
        assert result.is_error

    def test_utf8_content(self, context, tmp_dir):
        """UTF-8 中文内容正确编辑"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("你好世界", encoding="utf-8")
        result = execute_file_edit(
            {"file_path": "test.txt", "old_string": "你好", "new_string": "您好"},
            context,
        )
        assert not result.is_error
        assert file_path.read_text(encoding="utf-8") == "您好世界"

    def test_empty_old_string_multiple_matches(self, context, tmp_dir):
        """old_string 为空字符串时匹配多个位置，replace_all=False 报错"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("world", encoding="utf-8")
        result = execute_file_edit(
            {"file_path": "test.txt", "old_string": "", "new_string": "hello "},
            context,
        )
        # 空字符串在每个位置都匹配，count > 1，应报错
        assert result.is_error
        assert "多个" in result.output

    def test_empty_old_string_with_replace_all(self, context, tmp_dir):
        """old_string 为空字符串且 replace_all=True 时，在每个位置插入"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("ab", encoding="utf-8")
        result = execute_file_edit(
            {
                "file_path": "test.txt",
                "old_string": "",
                "new_string": "x",
                "replace_all": True,
            },
            context,
        )
        assert not result.is_error
        # 空字符串在 a 前、a 和 b 之间、b 后各匹配一次 -> "xaxbx"
        assert file_path.read_text(encoding="utf-8") == "xaxbx"

    def test_file_not_exists(self, context):
        """文件不存在返回错误"""
        result = execute_file_edit(
            {"file_path": "nonexistent.txt", "old_string": "a", "new_string": "b"},
            context,
        )
        assert result.is_error
        assert "不存在" in result.output

    def test_path_is_directory(self, context, tmp_dir):
        """路径是目录返回错误"""
        dir_path = tmp_dir / "test_dir"
        dir_path.mkdir()
        result = execute_file_edit(
            {"file_path": "test_dir", "old_string": "a", "new_string": "b"}, context
        )
        assert result.is_error
        assert "目录" in result.output

    def test_old_string_not_in_file(self, context, tmp_dir):
        """old_string 不在文件中返回错误"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello world", encoding="utf-8")
        result = execute_file_edit(
            {"file_path": "test.txt", "old_string": "not_exist", "new_string": "b"},
            context,
        )
        assert result.is_error
        assert "不存在" in result.output

    def test_abort(self, context, tmp_dir):
        """中断文件编辑"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello world", encoding="utf-8")
        context.abort_controller.abort()
        result = execute_file_edit(
            {"file_path": "test.txt", "old_string": "hello", "new_string": "hi"},
            context,
        )
        assert result.is_error
        assert "取消" in result.output

    def test_cache_update(self, context, tmp_dir):
        """编辑后更新缓存"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text("hello world", encoding="utf-8")
        abs_path = str(file_path)

        result = execute_file_edit(
            {"file_path": "test.txt", "old_string": "hello", "new_string": "hi"},
            context,
        )
        assert not result.is_error

        cached = context.file_read_state.get(abs_path)
        assert cached is not None
        content, _ = cached
        assert content == "hi world"

    def test_multiline_edit(self, context, tmp_dir):
        """多行文本替换"""
        file_path = tmp_dir / "test.txt"
        file_path.write_text(
            "def hello():\n    print('hello')\n", encoding="utf-8"
        )
        result = execute_file_edit(
            {
                "file_path": "test.txt",
                "old_string": "def hello():\n    print('hello')",
                "new_string": "def hello(name):\n    print(f'hello {name}')",
            },
            context,
        )
        assert not result.is_error
        content = file_path.read_text(encoding="utf-8")
        assert "def hello(name):" in content
        assert "print(f'hello {name}')" in content


# ============================================================
# 工具属性测试
# ============================================================


class TestFileEditTool:
    """工具属性测试"""

    def test_tool_name(self):
        """工具名称正确"""
        assert file_edit_tool.name == "edit"

    def test_tool_description(self):
        """工具描述包含编辑关键词"""
        assert "修改" in file_edit_tool.description

    def test_tool_parameters(self):
        """工具参数定义正确"""
        assert "file_path" in file_edit_tool.parameters["properties"]
        assert "old_string" in file_edit_tool.parameters["properties"]
        assert "new_string" in file_edit_tool.parameters["properties"]
        assert "replace_all" in file_edit_tool.parameters["properties"]

    def test_not_read_only(self):
        """Edit 工具不是只读的"""
        assert not file_edit_tool.is_read_only({})

    def test_not_concurrency_safe(self):
        """Edit 工具不支持并发"""
        assert not file_edit_tool.is_concurrency_safe({})

    def test_is_enabled(self):
        """Edit 工具默认启用"""
        assert file_edit_tool.is_enabled()

    def test_is_not_destructive(self):
        """Edit 工具默认非破坏性"""
        assert not file_edit_tool.is_destructive({})

    def test_get_summary(self):
        """获取摘要"""
        summary = file_edit_tool.get_summary({"file_path": "test.txt"})
        assert summary is not None
        assert "test.txt" in summary

    def test_get_user_facing_name(self):
        """获取用户可见名称"""
        name = file_edit_tool.get_user_facing_name({})
        assert name == "Edit"

    def test_get_activity_description(self):
        """获取活动描述"""
        desc = file_edit_tool.get_activity_description({"file_path": "test.txt"})
        assert desc is not None
        assert "test.txt" in desc
