"""SystemPromptBuilder 测试"""

from agent.prompts.builder import SystemPromptBuilder


class TestBuildPrefix:
    """build_prefix() 测试"""

    def test_contains_identity(self) -> None:
        """包含 identity 内容"""
        result = SystemPromptBuilder.build_prefix()
        assert "Cool Code" in result

    def test_contains_behavior_guidelines(self) -> None:
        """包含行为准则"""
        result = SystemPromptBuilder.build_prefix()
        assert "行为准则" in result

    def test_contains_tool_selection_guide(self) -> None:
        """包含工具选择指南"""
        result = SystemPromptBuilder.build_prefix()
        assert "工具选择指南" in result

    def test_no_memory_content(self) -> None:
        """不包含 memory 相关内容"""
        result = SystemPromptBuilder.build_prefix()
        # build_prefix 不应调用 memory.render()
        assert "Memory:" not in result
        assert "task:" not in result.split("行为准则")[0]  # 不在 identity 部分

    def test_no_tool_list(self) -> None:
        """不包含工具列表"""
        result = SystemPromptBuilder.build_prefix()
        assert "可用工具:" not in result

    def test_no_subagent_guide(self) -> None:
        """不包含 SubAgent 指南"""
        result = SystemPromptBuilder.build_prefix()
        assert "SubAgent" not in result

    def test_stable_output(self) -> None:
        """多次调用返回相同内容"""
        r1 = SystemPromptBuilder.build_prefix()
        r2 = SystemPromptBuilder.build_prefix()
        assert r1 == r2

    def test_build_uses_prefix(self) -> None:
        """build() 的静态部分与 build_prefix() 一致"""
        prefix = SystemPromptBuilder.build_prefix()
        full = SystemPromptBuilder.build()
        # build() 的开头应该包含 prefix 的所有内容
        assert prefix in full
