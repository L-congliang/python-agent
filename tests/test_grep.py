"""Grep 工具测试 - 基础结构验证"""

from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

from agent.core.context import AbortController, ToolUseContext
from agent.core.types import ValidationResult
from agent.tools.grep import (
    _check_ripgrep_installed,
    _resolve_path,
    _build_rg_command,
    _parse_rg_output,
    execute_grep,
    validate_grep_input,
    GREP_PARAMETERS,
    DEFAULT_MAX_RESULTS,
)


# ============================================================
# 导入和基础结构验证
# ============================================================


class TestImports:
    """验证所有导入正确"""

    def test_import_check_ripgrep_installed(self):
        """_check_ripgrep_installed 可以导入"""
        assert callable(_check_ripgrep_installed)

    def test_import_resolve_path(self):
        """_resolve_path 可以导入"""
        assert callable(_resolve_path)

    def test_import_grep_parameters(self):
        """GREP_PARAMETERS 可以导入"""
        assert isinstance(GREP_PARAMETERS, dict)

    def test_import_default_max_results(self):
        """DEFAULT_MAX_RESULTS 可以导入"""
        assert isinstance(DEFAULT_MAX_RESULTS, int)

    def test_import_execute_grep(self):
        """execute_grep 可以导入"""
        assert callable(execute_grep)


# ============================================================
# _check_ripgrep_installed 测试
# ============================================================


class TestCheckRipgrepInstalled:
    """ripgrep 安装检测测试"""

    @patch("shutil.which", return_value="/usr/bin/rg")
    def test_returns_true_when_installed(self, mock_which):
        """rg 存在时返回 True"""
        assert _check_ripgrep_installed() is True

    @patch("shutil.which", return_value=None)
    def test_returns_false_when_not_installed(self, mock_which):
        """rg 不存在时返回 False"""
        assert _check_ripgrep_installed() is False


# ============================================================
# _resolve_path 测试
# ============================================================


class TestResolvePath:
    """路径解析测试"""

    def test_absolute_path_unchanged(self):
        """绝对路径不变"""
        result = _resolve_path("/tmp/test", "/home/user")
        assert result == "/tmp/test"

    def test_relative_path_resolved(self):
        """相对路径基于 cwd 解析"""
        result = _resolve_path("src/main.py", "/home/user/project")
        assert result == os.path.abspath("/home/user/project/src/main.py")

    def test_empty_path_resolved(self):
        """空路径解析为 cwd"""
        result = _resolve_path("", "/home/user/project")
        assert result == os.path.abspath("/home/user/project")

    def test_dot_path_resolved(self):
        """当前目录路径解析"""
        result = _resolve_path(".", "/home/user/project")
        assert result == os.path.abspath("/home/user/project")


# ============================================================
# GREP_PARAMETERS 测试
# ============================================================


class TestGrepParameters:
    """参数定义测试"""

    def test_type_is_object(self):
        """参数 schema 类型为 object"""
        assert GREP_PARAMETERS["type"] == "object"

    def test_required_fields(self):
        """pattern 是必填字段"""
        assert "pattern" in GREP_PARAMETERS["required"]

    def test_pattern_property(self):
        """pattern 属性定义正确"""
        props = GREP_PARAMETERS["properties"]
        assert "pattern" in props
        assert props["pattern"]["type"] == "string"

    def test_path_property(self):
        """path 属性定义正确"""
        props = GREP_PARAMETERS["properties"]
        assert "path" in props
        assert props["path"]["type"] == "string"

    def test_include_property(self):
        """include 属性定义正确"""
        props = GREP_PARAMETERS["properties"]
        assert "include" in props
        assert props["include"]["type"] == "string"

    def test_max_results_property(self):
        """max_results 属性定义正确"""
        props = GREP_PARAMETERS["properties"]
        assert "max_results" in props
        assert props["max_results"]["type"] == "integer"
        assert props["max_results"]["default"] == DEFAULT_MAX_RESULTS

    def test_case_sensitive_property(self):
        """case_sensitive 属性定义正确"""
        props = GREP_PARAMETERS["properties"]
        assert "case_sensitive" in props
        assert props["case_sensitive"]["type"] == "boolean"
        assert props["case_sensitive"]["default"] is False

    def test_context_lines_property(self):
        """context_lines 属性定义正确"""
        props = GREP_PARAMETERS["properties"]
        assert "context_lines" in props
        assert props["context_lines"]["type"] == "integer"
        assert props["context_lines"]["default"] == 0

    def test_all_expected_properties_present(self):
        """所有预期属性都存在"""
        expected = {"pattern", "path", "include", "max_results", "case_sensitive", "context_lines"}
        actual = set(GREP_PARAMETERS["properties"].keys())
        assert expected == actual

    def test_default_max_results_value(self):
        """默认最大结果数为 100"""
        assert DEFAULT_MAX_RESULTS == 100


# ============================================================
# _build_rg_command 测试
# ============================================================


class TestBuildRgCommand:
    """ripgrep 命令构造测试"""

    def test_basic_command(self):
        """测试基本的命令构造"""
        cmd = _build_rg_command(
            pattern="TODO",
            path="src/",
            include=None,
            max_results=100,
            case_sensitive=False,
            context_lines=0,
        )
        assert "rg" in cmd
        assert "--line-number" in cmd
        assert "--with-filename" in cmd
        assert "--no-heading" in cmd
        assert "TODO" in cmd
        assert "src/" in cmd

    def test_with_include(self):
        """测试带文件过滤的命令构造"""
        cmd = _build_rg_command(
            pattern="TODO",
            path="src/",
            include="*.py",
            max_results=100,
            case_sensitive=False,
            context_lines=0,
        )
        assert "--glob" in cmd
        assert "*.py" in cmd

    def test_case_sensitive(self):
        """测试大小写敏感的命令构造"""
        cmd = _build_rg_command(
            pattern="TODO",
            path="src/",
            include=None,
            max_results=100,
            case_sensitive=True,
            context_lines=0,
        )
        assert "--case-sensitive" in cmd
        assert "--case-insensitive" not in cmd

    def test_case_insensitive(self):
        """测试大小写不敏感的命令构造"""
        cmd = _build_rg_command(
            pattern="TODO",
            path="src/",
            include=None,
            max_results=100,
            case_sensitive=False,
            context_lines=0,
        )
        assert "--case-insensitive" in cmd

    def test_context_lines(self):
        """测试带上下文的命令构造"""
        cmd = _build_rg_command(
            pattern="TODO",
            path="src/",
            include=None,
            max_results=100,
            case_sensitive=False,
            context_lines=2,
        )
        assert "--context" in cmd
        assert "2" in cmd

    def test_max_results(self):
        """测试最大结果数参数"""
        cmd = _build_rg_command(
            pattern="TODO",
            path="src/",
            include=None,
            max_results=50,
            case_sensitive=False,
            context_lines=0,
        )
        assert "--max-count" in cmd
        assert "50" in cmd

    def test_all_options(self):
        """测试所有选项组合"""
        cmd = _build_rg_command(
            pattern="test.*pattern",
            path="tests/",
            include="*.test.py",
            max_results=200,
            case_sensitive=True,
            context_lines=3,
        )
        assert cmd[0] == "rg"
        assert "--line-number" in cmd
        assert "--with-filename" in cmd
        assert "--no-heading" in cmd
        assert "--max-count" in cmd
        assert "200" in cmd
        assert "--glob" in cmd
        assert "*.test.py" in cmd
        assert "--context" in cmd
        assert "3" in cmd
        assert "test.*pattern" in cmd
        assert "tests/" in cmd


# ============================================================
# _parse_rg_output 测试
# ============================================================


class TestParseRgOutput:
    """ripgrep 输出解析测试"""

    def test_basic_output(self):
        """测试基本的输出解析"""
        output = "src/main.py:15:# TODO: implement this\nsrc/utils.py:42:# TODO: fix bug\n"
        results = _parse_rg_output(output)
        assert len(results) == 2
        assert results[0]["file"] == "src/main.py"
        assert results[0]["line"] == 15
        assert results[0]["content"] == "# TODO: implement this"
        assert results[1]["file"] == "src/utils.py"
        assert results[1]["line"] == 42
        assert results[1]["content"] == "# TODO: fix bug"

    def test_empty_output(self):
        """测试空输出"""
        output = ""
        results = _parse_rg_output(output)
        assert len(results) == 0

    def test_no_match(self):
        """测试无匹配结果"""
        output = ""
        results = _parse_rg_output(output)
        assert len(results) == 0

    def test_single_result(self):
        """测试单个结果"""
        output = "README.md:1:# Project Title\n"
        results = _parse_rg_output(output)
        assert len(results) == 1
        assert results[0]["file"] == "README.md"
        assert results[0]["line"] == 1
        assert results[0]["content"] == "# Project Title"

    def test_content_with_colons(self):
        """测试内容中包含冒号"""
        output = "config.py:10:DATABASE_URL = 'postgresql://user:pass@host/db'\n"
        results = _parse_rg_output(output)
        assert len(results) == 1
        assert results[0]["file"] == "config.py"
        assert results[0]["line"] == 10
        assert results[0]["content"] == "DATABASE_URL = 'postgresql://user:pass@host/db'"

    def test_windows_path(self):
        """测试 Windows 路径格式"""
        output = "src\\main.py:15:print('hello')\n"
        results = _parse_rg_output(output)
        assert len(results) == 1
        assert results[0]["file"] == "src\\main.py"
        assert results[0]["line"] == 15
        assert results[0]["content"] == "print('hello')"

    def test_malformed_line_skipped(self):
        """测试格式错误的行被跳过"""
        output = "valid.py:1:code\nnot_a_match\nalso_valid.py:2:more code\n"
        results = _parse_rg_output(output)
        assert len(results) == 2
        assert results[0]["file"] == "valid.py"
        assert results[1]["file"] == "also_valid.py"

    def test_invalid_line_number_skipped(self):
        """测试行号无效时跳过"""
        output = "file.py:not_a_number:content\n"
        results = _parse_rg_output(output)
        assert len(results) == 0


# ============================================================
# execute_grep 测试
# ============================================================


def _make_context(cwd: str = ".") -> ToolUseContext:
    """创建测试用的 ToolUseContext"""
    return ToolUseContext(
        model="test",
        cwd=cwd,
        abort_controller=AbortController(),
    )


class TestExecuteGrep:
    """execute_grep 核心逻辑测试"""

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=False)
    def test_ripgrep_not_installed(self, mock_check):
        """ripgrep 未安装时返回错误"""
        context = _make_context("/test")
        result = execute_grep({"pattern": "TODO"}, context)
        assert result.is_error is True
        assert "ripgrep" in result.output
        assert "安装" in result.output

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=False)
    def test_path_not_exists(self, mock_exists, mock_check):
        """路径不存在时返回错误"""
        context = _make_context("/test")
        result = execute_grep({"pattern": "TODO", "path": "/nonexistent"}, context)
        assert result.is_error is True
        assert "不存在" in result.output

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    def test_abort_returns_error(self, mock_check):
        """中断时返回错误"""
        context = _make_context("/test")
        context.abort_controller.abort()
        result = execute_grep({"pattern": "TODO"}, context)
        assert result.is_error is True
        assert "取消" in result.output

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=True)
    @patch("agent.tools.grep.subprocess.run")
    def test_basic_search(self, mock_run, mock_exists, mock_check):
        """基本搜索功能"""
        mock_result = MagicMock()
        mock_result.stdout = "src/main.py:15:# TODO: implement this\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        context = _make_context("/test")
        result = execute_grep({"pattern": "TODO"}, context)
        assert result.is_error is False
        assert "src/main.py:15:# TODO: implement this" in result.output

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=True)
    @patch("agent.tools.grep.subprocess.run")
    def test_multiple_results(self, mock_run, mock_exists, mock_check):
        """多个搜索结果"""
        mock_result = MagicMock()
        mock_result.stdout = (
            "src/main.py:15:# TODO: first\n"
            "src/utils.py:42:# TODO: second\n"
        )
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        context = _make_context("/test")
        result = execute_grep({"pattern": "TODO"}, context)
        assert result.is_error is False
        assert "src/main.py:15:# TODO: first" in result.output
        assert "src/utils.py:42:# TODO: second" in result.output

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=True)
    @patch("agent.tools.grep.subprocess.run")
    def test_no_matches_returncode_1(self, mock_run, mock_exists, mock_check):
        """无匹配结果（ripgrep 返回 1）"""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        context = _make_context("/test")
        result = execute_grep({"pattern": "NOTFOUND"}, context)
        assert result.is_error is False
        assert "No matches" in result.output

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=True)
    @patch("agent.tools.grep.subprocess.run")
    def test_no_matches_empty_output(self, mock_run, mock_exists, mock_check):
        """无匹配结果（返回码 0 但输出为空）"""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        context = _make_context("/test")
        result = execute_grep({"pattern": "NOTFOUND"}, context)
        assert result.is_error is False
        assert "No matches" in result.output

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=True)
    @patch("agent.tools.grep.subprocess.run")
    def test_timeout(self, mock_run, mock_exists, mock_check):
        """搜索超时"""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="rg", timeout=30)

        context = _make_context("/test")
        result = execute_grep({"pattern": "TODO"}, context)
        assert result.is_error is True
        assert "超时" in result.output

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=True)
    @patch("agent.tools.grep.subprocess.run")
    def test_rg_error(self, mock_run, mock_exists, mock_check):
        """ripgrep 执行错误"""
        mock_result = MagicMock()
        mock_result.returncode = 2
        mock_result.stderr = "regex parse error"
        mock_run.return_value = mock_result

        context = _make_context("/test")
        result = execute_grep({"pattern": "[invalid"}, context)
        assert result.is_error is True
        assert "搜索失败" in result.output
        assert "regex parse error" in result.output

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=True)
    @patch("agent.tools.grep.subprocess.run")
    def test_default_path_is_cwd(self, mock_run, mock_exists, mock_check):
        """默认搜索路径是 cwd"""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        context = _make_context("/my/project")
        execute_grep({"pattern": "TODO"}, context)
        # 验证 subprocess.run 被调用，且命令中包含 cwd 路径
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "/my/project" in cmd

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=True)
    @patch("agent.tools.grep.subprocess.run")
    def test_with_include(self, mock_run, mock_exists, mock_check):
        """带文件过滤的搜索"""
        mock_result = MagicMock()
        mock_result.stdout = "src/main.py:1:hello\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        context = _make_context("/test")
        result = execute_grep({"pattern": "hello", "include": "*.py"}, context)
        assert result.is_error is False
        # 验证命令中包含 --glob 参数
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "--glob" in cmd
        assert "*.py" in cmd

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=True)
    @patch("agent.tools.grep.subprocess.run")
    def test_unexpected_exception(self, mock_run, mock_exists, mock_check):
        """未预期的异常被捕获"""
        mock_run.side_effect = OSError("disk error")

        context = _make_context("/test")
        result = execute_grep({"pattern": "TODO"}, context)
        assert result.is_error is True
        assert "搜索失败" in result.output
        assert "disk error" in result.output


# ============================================================
# validate_grep_input 测试
# ============================================================


class TestValidateGrepInput:
    """validate_grep_input 输入校验测试"""

    def test_valid_input(self):
        """有效输入校验通过"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO"}, context)
        assert result.is_valid is True

    def test_empty_pattern(self):
        """空 pattern 校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": ""}, context)
        assert result.is_valid is False
        assert "pattern" in result.message

    def test_missing_pattern(self):
        """缺少 pattern 校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({}, context)
        assert result.is_valid is False
        assert "pattern" in result.message

    def test_whitespace_only_pattern(self):
        """纯空格 pattern 校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "   "}, context)
        assert result.is_valid is False
        assert "pattern" in result.message

    def test_invalid_pattern_type(self):
        """非字符串 pattern 校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": 123}, context)
        assert result.is_valid is False
        assert "pattern" in result.message

    def test_invalid_max_results_negative(self):
        """负数 max_results 校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO", "max_results": -1}, context)
        assert result.is_valid is False
        assert "max_results" in result.message

    def test_invalid_max_results_zero(self):
        """零 max_results 校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO", "max_results": 0}, context)
        assert result.is_valid is False
        assert "max_results" in result.message

    def test_invalid_max_results_type(self):
        """非整数 max_results 校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO", "max_results": "abc"}, context)
        assert result.is_valid is False
        assert "max_results" in result.message

    def test_invalid_context_lines_negative(self):
        """负数 context_lines 校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO", "context_lines": -1}, context)
        assert result.is_valid is False
        assert "context_lines" in result.message

    def test_invalid_context_lines_type(self):
        """非整数 context_lines 校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO", "context_lines": 1.5}, context)
        assert result.is_valid is False
        assert "context_lines" in result.message

    def test_empty_path_string(self):
        """空字符串 path 校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO", "path": ""}, context)
        assert result.is_valid is False
        assert "path" in result.message

    def test_whitespace_only_path(self):
        """纯空格 path 校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO", "path": "   "}, context)
        assert result.is_valid is False
        assert "path" in result.message

    def test_invalid_path_type(self):
        """非字符串 path 校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO", "path": 123}, context)
        assert result.is_valid is False
        assert "path" in result.message

    @patch("agent.tools.grep.os.path.exists", return_value=False)
    def test_path_not_exists(self, mock_exists):
        """不存在的路径校验失败"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO", "path": "/nonexistent"}, context)
        assert result.is_valid is False
        assert "不存在" in result.message

    @patch("agent.tools.grep.os.path.exists", return_value=True)
    def test_valid_path(self, mock_exists):
        """有效路径校验通过"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO", "path": "/some/path"}, context)
        assert result.is_valid is True

    def test_valid_max_results(self):
        """有效 max_results 校验通过"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO", "max_results": 50}, context)
        assert result.is_valid is True

    def test_valid_context_lines(self):
        """有效 context_lines 校验通过"""
        context = _make_context("/test")
        result = validate_grep_input({"pattern": "TODO", "context_lines": 3}, context)
        assert result.is_valid is True

    def test_valid_all_params(self):
        """所有有效参数校验通过"""
        context = _make_context("/test")
        result = validate_grep_input({
            "pattern": "TODO",
            "max_results": 50,
            "context_lines": 2,
        }, context)
        assert result.is_valid is True


# ============================================================
# grep_tool 工具属性测试
# ============================================================


class TestGrepTool:
    """grep_tool 工具属性测试"""

    def test_tool_name(self):
        """工具名称为 grep"""
        from agent.tools.grep import grep_tool
        assert grep_tool.name == "grep"

    def test_tool_description(self):
        """工具描述包含关键词"""
        from agent.tools.grep import grep_tool
        desc = grep_tool.description
        assert "搜索" in desc or "search" in desc.lower()

    def test_tool_parameters_schema(self):
        """参数 Schema 包含 pattern 等字段"""
        from agent.tools.grep import grep_tool
        props = grep_tool.parameters["properties"]
        assert "pattern" in props
        assert "path" in props
        assert "include" in props
        assert "max_results" in props
        assert "case_sensitive" in props
        assert "context_lines" in props
        assert grep_tool.parameters["required"] == ["pattern"]

    def test_is_read_only(self):
        """grep 是只读工具"""
        from agent.tools.grep import grep_tool
        assert grep_tool.is_read_only({}) is True

    def test_is_concurrency_safe(self):
        """grep 支持并发"""
        from agent.tools.grep import grep_tool
        assert grep_tool.is_concurrency_safe({}) is True

    def test_is_not_destructive(self):
        """grep 不是破坏性工具"""
        from agent.tools.grep import grep_tool
        assert grep_tool.is_destructive({}) is False

    def test_get_summary(self):
        """摘要包含搜索模式"""
        from agent.tools.grep import grep_tool
        summary = grep_tool.get_summary({"pattern": "TODO"})
        assert "TODO" in summary

    def test_get_user_facing_name(self):
        """用户可见名称为 Grep"""
        from agent.tools.grep import grep_tool
        assert grep_tool.get_user_facing_name({}) == "Grep"

    def test_get_activity_description(self):
        """活动描述包含搜索模式"""
        from agent.tools.grep import grep_tool
        desc = grep_tool.get_activity_description({"pattern": "TODO"})
        assert "TODO" in desc

    def test_validate_input_delegates(self):
        """validate_input 正确委托"""
        from agent.tools.grep import grep_tool
        # 空 pattern 应该失败
        result = grep_tool.validate_input(
            {"pattern": ""}, _make_context("/test")
        )
        assert not result.is_valid

    def test_execute_delegates(self):
        """execute 正确委托到 execute_grep"""
        from agent.tools.grep import grep_tool
        with (
            patch("agent.tools.grep._check_ripgrep_installed", return_value=True),
            patch("agent.tools.grep.os.path.exists", return_value=True),
            patch("agent.tools.grep.subprocess.run") as mock_run,
        ):
            mock_result = MagicMock()
            mock_result.stdout = "src/main.py:1:hello\n"
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            context = _make_context("/test")
            result = grep_tool.execute({"pattern": "hello"}, context)
            assert result.is_error is False
            assert "hello" in result.output


# ============================================================
# execute_grep 补充测试
# ============================================================


class TestExecuteGrepAdditional:
    """execute_grep 补充测试用例"""

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=True)
    @patch("agent.tools.grep.subprocess.run")
    def test_execute_grep_with_include(self, mock_run, mock_exists, mock_check):
        """测试带文件过滤的搜索 - 验证命令参数"""
        mock_result = MagicMock()
        mock_result.stdout = "src/main.py:15:# TODO: implement this\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        context = _make_context("/test")
        result = execute_grep({"pattern": "TODO", "include": "*.py"}, context)
        assert result.is_error is False
        # 验证命令中包含 --glob *.py
        call_args = mock_run.call_args[0][0]
        assert "--glob" in call_args
        assert "*.py" in call_args

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=True)
    @patch("agent.tools.grep.subprocess.run")
    def test_execute_grep_case_sensitive(self, mock_run, mock_exists, mock_check):
        """测试大小写敏感搜索 - 验证命令参数"""
        mock_result = MagicMock()
        mock_result.stdout = "src/main.py:15:# TODO: implement this\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        context = _make_context("/test")
        result = execute_grep({"pattern": "TODO", "case_sensitive": True}, context)
        assert result.is_error is False
        # 验证命令中包含 --case-sensitive
        call_args = mock_run.call_args[0][0]
        assert "--case-sensitive" in call_args

    @patch("agent.tools.grep._check_ripgrep_installed", return_value=True)
    @patch("agent.tools.grep.os.path.exists", return_value=True)
    @patch("agent.tools.grep.subprocess.run")
    def test_execute_grep_no_matches(self, mock_run, mock_exists, mock_check):
        """测试无匹配结果 - 返回码 1"""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        context = _make_context("/test")
        result = execute_grep({"pattern": "NONEXISTENT"}, context)
        assert result.is_error is False
        assert "No matches found" in result.output
