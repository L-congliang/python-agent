"""F05 Bash 工具测试"""

import pytest

from agent.core.context import ToolUseContext
from agent.tools.bash import (
    _detect_shell,
    _shell_cache,
    _truncate_output,
    MAX_OUTPUT_LINES,
    validate_bash_input,
)


class TestDetectShell:
    """Shell 检测测试"""

    def test_detect_shell_returns_valid_tuple(self):
        """检测结果是 (executable, arg_prefix) 格式"""
        shell_exe, shell_arg = _detect_shell()
        assert isinstance(shell_exe, str)
        assert len(shell_exe) > 0
        assert shell_arg in ("-c", "/c")

    def test_detect_shell_finds_bash_on_windows(self):
        """Windows 上应该能找到 bash（Git Bash）或 fallback 到 cmd"""
        shell_exe, shell_arg = _detect_shell()
        # 只要能检测到 shell 就行
        assert shell_exe

    def test_detect_shell_cache(self):
        """检测结果被缓存，多次调用返回同一个对象"""
        result1 = _detect_shell()
        result2 = _detect_shell()
        assert result1 is result2



class TestTruncateOutput:
    """输出截断测试"""

    def test_short_output_not_truncated(self):
        """短输出不截断"""
        output = "hello\nworld"
        assert _truncate_output(output) == output

    def test_exact_limit_not_truncated(self):
        """刚好等于上限时不截断"""
        output = "\n".join(f"line {i}" for i in range(MAX_OUTPUT_LINES))
        result = _truncate_output(output)
        assert "truncated" not in result

    def test_long_output_truncated(self):
        """超过上限时截断，保留尾部"""
        lines = [f"line {i}" for i in range(3000)]
        output = "\n".join(lines)
        result = _truncate_output(output)
        assert "truncated 1000 lines" in result
        assert "line 2999" in result  # 尾部保留
        assert "line 0" not in result  # 头部被截断

    def test_truncated_has_header(self):
        """截断后有提示行"""
        output = "\n".join(f"line {i}" for i in range(3000))
        result = _truncate_output(output)
        assert result.startswith("... (truncated")

    def test_custom_max_lines(self):
        """支持自定义 max_lines"""
        output = "\n".join(f"line {i}" for i in range(100))
        result = _truncate_output(output, max_lines=10)
        assert "truncated 90 lines" in result
        assert "line 99" in result


# ============================================================
# 输入校验测试
# ============================================================


@pytest.fixture
def context() -> ToolUseContext:
    """测试用的 ToolUseContext"""
    return ToolUseContext(model="test-model")


class TestValidateBashInput:
    """输入校验测试"""

    def test_valid_input(self, context):
        """合法输入校验通过"""
        result = validate_bash_input({"command": "ls -la"}, context)
        assert result.is_valid

    def test_valid_with_all_params(self, context):
        """所有参数都合法"""
        result = validate_bash_input(
            {"command": "ls", "timeout": 10, "workdir": "/tmp"},
            context,
        )
        assert result.is_valid

    def test_empty_command(self, context):
        """空命令校验失败"""
        result = validate_bash_input({"command": ""}, context)
        assert not result.is_valid
        assert "command" in result.message

    def test_missing_command(self, context):
        """缺少 command 校验失败"""
        result = validate_bash_input({}, context)
        assert not result.is_valid

    def test_none_command(self, context):
        """command 为 None 校验失败"""
        result = validate_bash_input({"command": None}, context)
        assert not result.is_valid

    def test_invalid_timeout_zero(self, context):
        """timeout 为 0 校验失败"""
        result = validate_bash_input(
            {"command": "ls", "timeout": 0}, context
        )
        assert not result.is_valid
        assert "timeout" in result.message

    def test_invalid_timeout_negative(self, context):
        """timeout 为负数校验失败"""
        result = validate_bash_input(
            {"command": "ls", "timeout": -1}, context
        )
        assert not result.is_valid

    def test_invalid_timeout_string(self, context):
        """timeout 为字符串校验失败"""
        result = validate_bash_input(
            {"command": "ls", "timeout": "abc"}, context
        )
        assert not result.is_valid

    def test_relative_workdir(self, context):
        """workdir 是相对路径校验失败"""
        result = validate_bash_input(
            {"command": "ls", "workdir": "relative/path"}, context
        )
        assert not result.is_valid
        assert "workdir" in result.message

    def test_absolute_workdir(self, context):
        """workdir 是绝对路径校验通过"""
        result = validate_bash_input(
            {"command": "ls", "workdir": "/tmp"}, context
        )
        assert result.is_valid
