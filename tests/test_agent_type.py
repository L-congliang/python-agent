"""Agent 类型系统测试"""

import pytest

from agent.orchestration.agent_type import AgentTypeDefinition, AgentTypeRegistry


class TestAgentTypeDefinition:
    """AgentTypeDefinition dataclass 测试"""

    def test_create_minimal(self) -> None:
        """只提供必填字段"""
        type_def = AgentTypeDefinition(
            name="test",
            description="Test type",
        )
        assert type_def.name == "test"
        assert type_def.description == "Test type"
        assert type_def.allowed_tools is None
        assert type_def.system_prompt is None
        assert type_def.default_model is None
        assert type_def.default_max_turns is None

    def test_create_full(self) -> None:
        """提供所有字段"""
        type_def = AgentTypeDefinition(
            name="test",
            description="Test type",
            allowed_tools=["read", "grep"],
            system_prompt="You are a test agent.",
            default_model="mimo-v2.5-pro",
            default_max_turns=10,
        )
        assert type_def.name == "test"
        assert type_def.allowed_tools == ["read", "grep"]
        assert type_def.system_prompt == "You are a test agent."
        assert type_def.default_model == "mimo-v2.5-pro"
        assert type_def.default_max_turns == 10

    def test_frozen(self) -> None:
        """AgentTypeDefinition 是不可变的"""
        type_def = AgentTypeDefinition(
            name="test",
            description="Test type",
        )
        with pytest.raises(AttributeError):
            type_def.name = "changed"  # type: ignore[misc]


class TestAgentTypeRegistry:
    """AgentTypeRegistry 测试"""

    def test_builtin_types_registered(self) -> None:
        """初始化时内置类型已注册"""
        registry = AgentTypeRegistry()
        assert registry.has("general-purpose")
        assert registry.has("explore")
        assert registry.has("code-reviewer")

    def test_get_existing_type(self) -> None:
        """获取已注册的类型"""
        registry = AgentTypeRegistry()
        type_def = registry.get("explore")
        assert type_def.name == "explore"
        assert type_def.allowed_tools == ["read", "grep", "glob", "bash"]

    def test_get_unknown_type_fallback(self) -> None:
        """获取不存在的类型，回退到 general-purpose"""
        registry = AgentTypeRegistry()
        type_def = registry.get("nonexistent")
        assert type_def.name == "general-purpose"

    def test_get_all(self) -> None:
        """获取所有类型"""
        registry = AgentTypeRegistry()
        all_types = registry.get_all()
        assert len(all_types) == 3
        names = {t.name for t in all_types}
        assert names == {"general-purpose", "explore", "code-reviewer"}

    def test_register_custom_type(self) -> None:
        """注册自定义类型"""
        registry = AgentTypeRegistry()
        custom = AgentTypeDefinition(
            name="custom",
            description="Custom type",
            allowed_tools=["read"],
        )
        registry.register(custom)
        assert registry.has("custom")
        assert registry.get("custom").allowed_tools == ["read"]

    def test_register_duplicate_raises(self) -> None:
        """注册重复类型名抛出 ValueError"""
        registry = AgentTypeRegistry()
        with pytest.raises(ValueError, match="已注册"):
            registry.register(AgentTypeDefinition(
                name="explore",
                description="Duplicate",
            ))

    def test_unregister(self) -> None:
        """注销类型"""
        registry = AgentTypeRegistry()
        registry.unregister("explore")
        assert not registry.has("explore")

    def test_unregister_nonexistent_raises(self) -> None:
        """注销不存在的类型抛出 KeyError"""
        registry = AgentTypeRegistry()
        with pytest.raises(KeyError):
            registry.unregister("nonexistent")

    def test_general_purpose_has_no_tool_filter(self) -> None:
        """general-purpose 类型不限制工具"""
        registry = AgentTypeRegistry()
        type_def = registry.get("general-purpose")
        assert type_def.allowed_tools is None

    def test_explore_default_max_turns(self) -> None:
        """explore 类型有默认轮次限制"""
        registry = AgentTypeRegistry()
        type_def = registry.get("explore")
        assert type_def.default_max_turns == 20

    def test_code_reviewer_read_only(self) -> None:
        """code-reviewer 类型只有读取工具"""
        registry = AgentTypeRegistry()
        type_def = registry.get("code-reviewer")
        assert "read" in type_def.allowed_tools
        assert "write" not in type_def.allowed_tools
        assert "edit" not in type_def.allowed_tools
