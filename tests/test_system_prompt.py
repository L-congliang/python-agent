"""System Prompt 优化测试

测试覆盖：
- SystemPromptBuilder.build_identity()
- SystemPromptBuilder.build_behavior_guidelines()
- SystemPromptBuilder.build_tool_selection_guide()
- SystemPromptBuilder.build_plan_mode_marker()
- SystemPromptBuilder.build_dynamic_context()
- SystemPromptBuilder.build()
"""

import pytest

from agent.prompts.builder import SystemPromptBuilder
from agent.tools.registry import ToolRegistry
from agent.tools.base import build_tool
from agent.core.types import ToolResult
from agent.memory.manager import MemoryManager


# ========== Identity 测试 ==========


class TestBuildIdentity:
    """Identity 部分测试"""

    def test_contains_agent_name(self):
        """Identity 包含 agent 名称"""
        identity = SystemPromptBuilder.build_identity()
        assert "Cool Code" in identity

    def test_contains_role_description(self):
        """Identity 包含角色描述"""
        identity = SystemPromptBuilder.build_identity()
        assert "终端" in identity or "AI" in identity

    def test_contains_capabilities(self):
        """Identity 包含能力列表"""
        identity = SystemPromptBuilder.build_identity()
        assert "文件" in identity
        assert "搜索" in identity or "代码" in identity
        assert "shell" in identity or "命令" in identity


# ========== Behavioral Guidelines 测试 ==========


class TestBuildBehaviorGuidelines:
    """Behavioral Guidelines 部分测试"""

    def test_contains_general_principles(self):
        """包含通用原则"""
        guidelines = SystemPromptBuilder.build_behavior_guidelines()
        assert "先理解" in guidelines
        assert "最小改动" in guidelines
        assert "出错" in guidelines

    def test_contains_specific_rules(self):
        """包含具体规则"""
        guidelines = SystemPromptBuilder.build_behavior_guidelines()
        assert "file_read" in guidelines
        assert "file_edit" in guidelines
        assert "grep" in guidelines

    def test_edit_over_write_rule(self):
        """包含 edit 优先于 write 的规则"""
        guidelines = SystemPromptBuilder.build_behavior_guidelines()
        assert "file_edit" in guidelines
        assert "file_write" in guidelines


# ========== Tool Selection Guide 测试 ==========


class TestBuildToolSelectionGuide:
    """Tool Selection Guide 部分测试"""

    def test_contains_tool_mapping(self):
        """包含工具选择映射"""
        guide = SystemPromptBuilder.build_tool_selection_guide()
        assert "file_read" in guide
        assert "file_edit" in guide
        assert "file_write" in guide
        assert "grep" in guide
        assert "glob" in guide
        assert "bash" in guide

    def test_contains_priority_rules(self):
        """包含工具优先级说明"""
        guide = SystemPromptBuilder.build_tool_selection_guide()
        assert "file_edit" in guide
        assert "file_write" in guide

    def test_grep_over_bash_grep(self):
        """包含 grep 优先于 bash grep 的说明"""
        guide = SystemPromptBuilder.build_tool_selection_guide()
        assert "grep" in guide
        assert "bash grep" in guide


# ========== Plan Mode Marker 测试 ==========


class TestBuildPlanModeMarker:
    """Plan Mode Marker 测试"""

    def test_contains_plan_mode_label(self):
        """包含计划模式标记"""
        marker = SystemPromptBuilder.build_plan_mode_marker()
        assert "计划模式" in marker

    def test_contains_plan_elements(self):
        """包含计划必要元素"""
        marker = SystemPromptBuilder.build_plan_mode_marker()
        assert "目标" in marker
        assert "步骤" in marker
        assert "工具" in marker

    def test_contains_wait_instruction(self):
        """包含等待确认指令"""
        marker = SystemPromptBuilder.build_plan_mode_marker()
        assert "等待" in marker or "确认" in marker


# ========== Dynamic Context 测试 ==========


class TestBuildDynamicContext:
    """Dynamic Context 部分测试"""

    def test_empty_when_no_inputs(self):
        """无输入时返回空字符串"""
        result = SystemPromptBuilder.build_dynamic_context()
        assert result == ""

    def test_includes_memory(self):
        """包含记忆信息"""
        memory = MemoryManager()
        memory.set_task("测试任务")
        result = SystemPromptBuilder.build_dynamic_context(memory=memory)
        assert "测试任务" in result

    def test_includes_tools(self):
        """包含工具列表"""
        registry = ToolRegistry()
        tool = build_tool(
            name="test_tool",
            description="测试工具",
            parameters={},
            execute_fn=lambda input, ctx: ToolResult(output="ok"),
        )
        registry.register(tool)
        result = SystemPromptBuilder.build_dynamic_context(registry=registry)
        assert "test_tool" in result
        assert "测试工具" in result

    def test_includes_subagent_guide(self):
        """包含 SubAgent 使用指南"""
        result = SystemPromptBuilder.build_dynamic_context(subagent_registered=True)
        assert "SubAgent" in result


# ========== Build 组装测试 ==========


class TestBuild:
    """SystemPromptBuilder.build() 组装测试"""

    def test_basic_build(self):
        """基本组装"""
        prompt = SystemPromptBuilder.build()
        assert "Cool Code" in prompt
        assert "行为准则" in prompt
        assert "工具选择指南" in prompt

    def test_build_with_memory(self):
        """带记忆的组装"""
        memory = MemoryManager()
        memory.set_task("修复 bug")
        prompt = SystemPromptBuilder.build(memory=memory)
        assert "修复 bug" in prompt

    def test_build_with_plan_mode(self):
        """Plan Mode 下的组装"""
        prompt = SystemPromptBuilder.build(plan_mode=True)
        assert "计划模式" in prompt

    def test_build_with_extra_prompt(self):
        """带额外 prompt 的组装"""
        prompt = SystemPromptBuilder.build(extra_prompt="自定义内容")
        assert "自定义内容" in prompt

    def test_identity_before_behavior(self):
        """Identity 在 Behavior 之前"""
        prompt = SystemPromptBuilder.build()
        identity_pos = prompt.find("Cool Code")
        behavior_pos = prompt.find("行为准则")
        assert identity_pos < behavior_pos

    def test_behavior_before_tool_guide(self):
        """Behavior 在 Tool Guide 之前"""
        prompt = SystemPromptBuilder.build()
        behavior_pos = prompt.find("行为准则")
        guide_pos = prompt.find("工具选择指南")
        assert behavior_pos < guide_pos
