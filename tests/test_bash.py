"""F05 Bash 工具测试"""

import pytest

from agent.core.context import ToolUseContext
from agent.core.types import ToolResult
from agent.tools.bash import (
    _detect_shell,
    _shell_cache,
    _truncate_output,
    execute_bash,
    MAX_OUTPUT_LINES,
    validate_bash_input,
    bash_tool,
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


# ============================================================
# 命令执行测试
# ============================================================

class TestExecuteBash:
    """命令执行测试"""

    def test_basic_command(self, context):
        """执行简单的 echo 命令"""
        result = execute_bash({"command": "echo hello"}, context)
        assert "hello" in result.output
        assert not result.is_error
        assert "[exit code: 0]" in result.output

    def test_command_failure(self, context):
        """执行失败的命令（ls 不存在的目录）"""
        result = execute_bash(
            {"command": "ls /nonexistent_dir_xyz"}, context
        )
        assert result.is_error
        assert "[exit code:" in result.output
        assert "[exit code: 0]" not in result.output

    def test_stderr_capture(self, context):
        """命令输出到 stderr"""
        result = execute_bash(
            {"command": "echo error_msg >&2"}, context
        )
        assert "[stderr]" in result.output
        assert "error_msg" in result.output

    def test_timeout(self, context):
        """命令超时"""
        result = execute_bash(
            {"command": "sleep 10", "timeout": 1}, context
        )
        assert result.is_error
        assert "超时" in result.output

    def test_workdir(self, context, tmp_path):
        """指定工作目录"""
        result = execute_bash(
            {"command": "pwd", "workdir": str(tmp_path)}, context
        )
        assert not result.is_error

    def test_abort(self, context):
        """中断命令执行"""
        context.abort_controller.abort()
        result = execute_bash({"command": "echo hello"}, context)
        assert result.is_error
        assert "取消" in result.output

    def test_special_characters(self, context):
        """命令包含特殊字符"""
        result = execute_bash(
            {"command": "echo 'hello world'"}, context
        )
        assert "hello world" in result.output
        assert not result.is_error

    def test_default_timeout(self, context):
        """默认 timeout 为 30 秒"""
        result = execute_bash({"command": "echo ok"}, context)
        assert not result.is_error

    def test_empty_output(self, context):
        """命令无输出时只有 exit code"""
        result = execute_bash({"command": "true"}, context)
        assert "[exit code: 0]" in result.output


# ============================================================
# bash_tool 工具属性测试
# ============================================================


class TestBashTool:
    """BashTool 工具属性测试"""

    def test_tool_name(self):
        """工具名称为 bash"""
        assert bash_tool.name == "bash"

    def test_tool_description(self):
        """工具描述包含关键词"""
        desc = bash_tool.description
        assert "shell" in desc.lower() or "命令" in desc

    def test_tool_parameters_schema(self):
        """参数 Schema 包含 command/timeout/workdir"""
        props = bash_tool.parameters["properties"]
        assert "command" in props
        assert "timeout" in props
        assert "workdir" in props
        assert bash_tool.parameters["required"] == ["command"]

    def test_is_not_read_only(self):
        """bash 不是只读工具"""
        assert not bash_tool.is_read_only({})

    def test_is_not_concurrency_safe(self):
        """bash 不支持并发"""
        assert not bash_tool.is_concurrency_safe({})

    def test_get_summary(self):
        """摘要包含命令内容"""
        summary = bash_tool.get_summary({"command": "ls -la"})
        assert "ls -la" in summary

    def test_get_summary_long_command(self):
        """长命令摘要被截断"""
        long_cmd = "a" * 100
        summary = bash_tool.get_summary({"command": long_cmd})
        assert len(summary) <= 60  # "Running: " + 50 chars

    def test_get_user_facing_name(self):
        """用户可见名称为 Bash"""
        assert bash_tool.get_user_facing_name({}) == "Bash"

    def test_get_activity_description(self):
        """活动描述包含命令"""
        desc = bash_tool.get_activity_description({"command": "pytest"})
        assert "pytest" in desc

    def test_validate_input_delegates(self):
        """validate_input 正确委托"""
        # 空命令应该失败
        result = bash_tool.validate_input(
            {"command": ""}, ToolUseContext(model="test")
        )
        assert not result.is_valid

    def test_execute_delegates(self, context):
        """execute 正确委托"""
        result = bash_tool.execute({"command": "echo test"}, context)
        assert "test" in result.output
        assert not result.is_error


# ============================================================
# 输出截断集成测试
# ============================================================


class TestOutputTruncationIntegration:
    """输出截断集成测试（通过 execute_bash 触发）"""

    def test_large_output_truncated(self, context):
        """大量输出被截断"""
        result = execute_bash(
            {"command": "for i in $(seq 1 3000); do echo line $i; done"},
            context,
        )
        assert "truncated" in result.output
        assert "line 3000" in result.output  # 尾部保留

    def test_small_output_not_truncated(self, context):
        """小量输出不截断"""
        result = execute_bash({"command": "echo hello"}, context)
        assert "truncated" not in result.output
        assert "hello" in result.output
