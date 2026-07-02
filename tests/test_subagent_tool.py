"""SubAgentTool 测试"""

import json

import pytest

from agent.tools.subagent import SubAgentTool, get_type_registry
from agent.core.types import ToolResult, ValidationResult
from agent.core.context import ToolUseContext


class TestSubAgentToolDefinition:
    """SubAgentTool 定义测试"""

    def test_name(self) -> None:
        """工具名称"""
        assert SubAgentTool.name == "subagent"

    def test_description(self) -> None:
        """工具描述"""
        assert "sub-agent" in SubAgentTool.description.lower()

    def test_parameters_schema(self) -> None:
        """参数 schema"""
        params = SubAgentTool.parameters
        assert params["type"] == "object"
        assert "prompt" in params["properties"]
        assert "description" in params["properties"]
        assert "agent_type" in params["properties"]
        assert "run_in_background" in params["properties"]
        assert "prompt" in params["required"]
        assert "description" in params["required"]

    def test_is_read_only(self) -> None:
        """SubAgentTool 是只读的"""
        assert SubAgentTool.is_read_only({}) is True


class TestSubAgentToolValidation:
    """SubAgentTool 输入校验测试"""

    def test_validate_valid_input(self) -> None:
        """有效输入"""
        # SubAgentTool 没有自定义 validate_input，使用默认的 success
        result = SubAgentTool.validate_input(
            {"prompt": "Search for TODOs", "description": "Search TODOs"},
            None,
        )
        assert result.is_valid is True

    def test_validate_empty_prompt(self) -> None:
        """空 prompt"""
        # 默认 validate_input 不校验，所以这个测试验证默认行为
        result = SubAgentTool.validate_input(
            {"prompt": "", "description": "Search TODOs"},
            None,
        )
        # 默认返回 success
        assert result.is_valid is True


class TestSubAgentToolPermissions:
    """SubAgentTool 权限检查测试"""

    def test_default_permissions(self) -> None:
        """默认权限检查"""
        result = SubAgentTool.check_permissions(
            {"prompt": "Search for TODOs", "description": "Search TODOs"},
            None,
        )
        # 默认返回 allow
        assert result.behavior.value == "allow"


class TestSubAgentToolSummary:
    """SubAgentTool 摘要测试"""

    def test_get_summary(self) -> None:
        """获取摘要"""
        summary = SubAgentTool.get_summary(
            {"description": "Search TODOs"}
        )
        assert "Search TODOs" in summary

    def test_get_activity_description(self) -> None:
        """获取活动描述"""
        desc = SubAgentTool.get_activity_description(
            {"description": "Search TODOs"}
        )
        assert "Search TODOs" in desc


class TestGetTypeRegistry:
    """get_type_registry 测试"""

    def test_returns_registry(self) -> None:
        """返回 AgentTypeRegistry"""
        registry = get_type_registry()
        assert registry is not None
        assert registry.has("general-purpose")
        assert registry.has("explore")
        assert registry.has("code-reviewer")

    def test_returns_same_instance(self) -> None:
        """返回同一个实例（单例）"""
        r1 = get_type_registry()
        r2 = get_type_registry()
        assert r1 is r2
