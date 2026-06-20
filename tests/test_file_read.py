"""F06 文件读取工具测试"""

import os

import pytest

from agent.tools.file_read import (
    _resolve_path,
    _detect_encoding,
    _format_with_line_numbers,
    _truncate_lines,
    MAX_LINES,
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
