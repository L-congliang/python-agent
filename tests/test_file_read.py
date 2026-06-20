"""F06 文件读取工具测试"""

import os

import pytest

from agent.core.context import ToolUseContext, AbortController, FileReadState
from agent.core.types import ToolResult
from agent.tools.file_read import (
    _resolve_path,
    _detect_encoding,
    _format_with_line_numbers,
    _truncate_lines,
    execute_file_read,
    validate_file_read_input,
    MAX_LINES,
)


def _make_context(cwd: str = ".") -> ToolUseContext:
    """创建测试用的 ToolUseContext"""
    return ToolUseContext(
        model="test",
        cwd=cwd,
        abort_controller=AbortController(),
        file_read_state=FileReadState(),
    )


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


class TestDetectEncoding:
    """编码检测测试"""

    def test_utf8_file(self, tmp_path):
        """UTF-8 文件检测"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello world", encoding="utf-8")
        encoding = _detect_encoding(str(file_path))
        assert encoding.lower().replace("-", "") in ("utf8", "ascii")

    def test_gbk_file(self, tmp_path):
        """GBK 文件检测"""
        file_path = tmp_path / "test.txt"
        # 使用较长的中文文本，chardet 需要足够多的字节才能高置信度检测
        text = "你好世界，这是一个用于编码检测的测试文件。" * 10
        file_path.write_bytes(text.encode("gbk"))
        encoding = _detect_encoding(str(file_path))
        # chardet 可能检测为 GB2312、GBK 或 GB18030，都是兼容的
        assert encoding.lower() in ("gbk", "gb2312", "gb18030")


class TestFormatWithLineNumbers:
    """行号格式化测试"""

    def test_basic_format(self):
        """基本行号格式"""
        content = "line1\nline2\nline3"
        result = _format_with_line_numbers(content, start_line=1)
        assert "1 │ line1" in result
        assert "2 │ line2" in result
        assert "3 │ line3" in result

    def test_custom_start_line(self):
        """自定义起始行号"""
        content = "line5\nline6"
        result = _format_with_line_numbers(content, start_line=5)
        assert "5 │ line5" in result
        assert "6 │ line6" in result

    def test_line_number_width_adapts(self):
        """行号宽度自动适配"""
        # 100 行文件，行号宽度应该是 3 位
        content = "\n".join(f"line {i}" for i in range(1, 101))
        result = _format_with_line_numbers(content, start_line=1)
        # 第一行应该是 "  1 │ line 1"（3位行号）
        assert "  1 │" in result
        # 第100行应该是 "100 │ line 100"
        assert "100 │" in result


class TestTruncateLines:
    """截断测试"""

    def test_short_content_not_truncated(self):
        """短内容不截断"""
        content = "line1\nline2\nline3"
        result = _truncate_lines(content)
        assert result == content

    def test_exact_limit_not_truncated(self):
        """刚好等于上限时不截断"""
        content = "\n".join(f"line {i}" for i in range(MAX_LINES))
        result = _truncate_lines(content)
        assert "truncated" not in result

    def test_long_content_truncated_keep_head(self):
        """超过上限时截断，保留头部"""
        lines = [f"line {i}" for i in range(3000)]
        content = "\n".join(lines)
        result = _truncate_lines(content)
        assert "truncated" in result
        assert "line 0" in result        # 头部保留
        assert "line 1999" in result      # 头部保留
        assert "line 2000" not in result  # 尾部截断


class TestExecuteFileRead:
    """文件读取执行测试"""

    def test_basic_text_read(self, tmp_path):
        """读取简单的文本文件"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello\nworld", encoding="utf-8")

        context = _make_context(str(tmp_path))
        result = execute_file_read({"file_path": "test.txt"}, context)

        assert not result.is_error
        assert "hello" in result.output
        assert "world" in result.output

    def test_line_numbers_in_output(self, tmp_path):
        """输出包含行号"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("line1\nline2", encoding="utf-8")

        context = _make_context(str(tmp_path))
        result = execute_file_read({"file_path": "test.txt"}, context)

        assert "│" in result.output
        assert "1 │ line1" in result.output
        assert "2 │ line2" in result.output

    def test_offset_and_limit(self, tmp_path):
        """指定行范围读取"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("a\nb\nc\nd\ne", encoding="utf-8")

        context = _make_context(str(tmp_path))
        result = execute_file_read(
            {"file_path": "test.txt", "offset": 2, "limit": 3},
            context,
        )

        assert not result.is_error
        assert "2 │ b" in result.output
        assert "3 │ c" in result.output
        assert "4 │ d" in result.output
        # 第 1 行和第 5 行不应该出现
        assert "1 │ a" not in result.output
        assert "5 │ e" not in result.output

    def test_file_not_found(self, tmp_path):
        """文件不存在时返回错误"""
        context = _make_context(str(tmp_path))
        result = execute_file_read(
            {"file_path": "nonexistent.txt"},
            context,
        )

        assert result.is_error
        assert "不存在" in result.output

    def test_path_is_directory(self, tmp_path):
        """路径是目录时返回错误"""
        context = _make_context(str(tmp_path))
        result = execute_file_read(
            {"file_path": str(tmp_path)},
            context,
        )

        assert result.is_error
        assert "目录" in result.output

    def test_abort(self, tmp_path):
        """中断文件读取"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content", encoding="utf-8")

        context = _make_context(str(tmp_path))
        context.abort_controller.abort()

        result = execute_file_read({"file_path": "test.txt"}, context)
        assert result.is_error
        assert "取消" in result.output

    def test_gbk_encoding(self, tmp_path):
        """读取 GBK 编码的中文文件"""
        file_path = tmp_path / "test.txt"
        # 使用较长的中文文本，chardet 需要足够多的字节才能高置信度检测
        text = "你好世界，这是一个用于编码检测的测试文件。" * 10
        file_path.write_bytes(text.encode("gbk"))

        context = _make_context(str(tmp_path))
        result = execute_file_read({"file_path": "test.txt"}, context)

        assert not result.is_error
        assert "你好世界" in result.output

    def test_cache_hit(self, tmp_path):
        """第二次读取使用缓存"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("cached content", encoding="utf-8")

        context = _make_context(str(tmp_path))
        result1 = execute_file_read({"file_path": "test.txt"}, context)
        result2 = execute_file_read({"file_path": "test.txt"}, context)

        assert result1.output == result2.output

    def test_cache_invalidation_on_mtime_change(self, tmp_path):
        """文件修改后缓存失效"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("old content", encoding="utf-8")

        context = _make_context(str(tmp_path))
        result1 = execute_file_read({"file_path": "test.txt"}, context)
        assert "old content" in result1.output

        # 修改文件
        import time
        time.sleep(0.01)  # 确保 mtime 变化
        file_path.write_text("new content", encoding="utf-8")

        result2 = execute_file_read({"file_path": "test.txt"}, context)
        assert "new content" in result2.output

    def test_large_file_truncation(self, tmp_path):
        """超过 2000 行时截断，保留头部"""
        file_path = tmp_path / "large.txt"
        content = "\n".join(f"line {i}" for i in range(3000))
        file_path.write_text(content, encoding="utf-8")

        context = _make_context(str(tmp_path))
        result = execute_file_read({"file_path": "large.txt"}, context)

        assert "truncated" in result.output
        assert "line 0" in result.output       # 头部保留
        assert "line 1999" in result.output     # 头部保留
        assert "line 2000" not in result.output # 尾部截断


class TestValidateFileReadInput:
    """输入校验测试"""

    def test_valid_input(self, tmp_path):
        """有效输入校验通过"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content", encoding="utf-8")

        context = _make_context(str(tmp_path))
        result = validate_file_read_input(
            {"file_path": "test.txt"},
            context,
        )
        assert result.is_valid

    def test_empty_path(self):
        """空路径校验失败"""
        context = _make_context()
        result = validate_file_read_input({"file_path": ""}, context)
        assert not result.is_valid

    def test_invalid_offset(self, tmp_path):
        """无效 offset 校验失败"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content", encoding="utf-8")

        context = _make_context(str(tmp_path))
        result = validate_file_read_input(
            {"file_path": "test.txt", "offset": -1},
            context,
        )
        assert not result.is_valid

    def test_invalid_limit(self, tmp_path):
        """无效 limit 校验失败"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content", encoding="utf-8")

        context = _make_context(str(tmp_path))
        result = validate_file_read_input(
            {"file_path": "test.txt", "limit": 0},
            context,
        )
        assert not result.is_valid
