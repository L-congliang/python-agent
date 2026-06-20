"""F05 Bash 工具测试"""

import pytest

from agent.tools.bash import _detect_shell, _shell_cache


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


from agent.tools.bash import _truncate_output, MAX_OUTPUT_LINES


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
