"""ToolRegistry 过滤和克隆测试"""

import pytest

from agent.tools.base import build_tool
from agent.tools.registry import ToolRegistry
from agent.core.types import ToolResult
from agent.core.context import ToolUseContext


def _make_tool(name: str) -> object:
    """创建测试工具"""
    return build_tool(
        name=name,
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}},
        execute_fn=lambda input, ctx: ToolResult(output="ok"),
    )


class TestFilterByNames:
    """filter_by_names 测试"""

    def test_filter_subset(self) -> None:
        """过滤出子集"""
        registry = ToolRegistry()
        registry.register(_make_tool("read"))
        registry.register(_make_tool("write"))
        registry.register(_make_tool("grep"))

        filtered = registry.filter_by_names(["read", "grep"])
        names = {t.name for t in filtered.get_all()}
        assert names == {"read", "grep"}

    def test_filter_empty_list(self) -> None:
        """空列表返回空注册表"""
        registry = ToolRegistry()
        registry.register(_make_tool("read"))

        filtered = registry.filter_by_names([])
        assert len(filtered.get_all()) == 0

    def test_filter_nonexistent_names(self) -> None:
        """不存在的名称被忽略"""
        registry = ToolRegistry()
        registry.register(_make_tool("read"))

        filtered = registry.filter_by_names(["read", "nonexistent"])
        names = {t.name for t in filtered.get_all()}
        assert names == {"read"}

    def test_filter_all_nonexistent(self) -> None:
        """所有名称都不存在"""
        registry = ToolRegistry()
        registry.register(_make_tool("read"))

        filtered = registry.filter_by_names(["foo", "bar"])
        assert len(filtered.get_all()) == 0

    def test_filter_preserves_tool_reference(self) -> None:
        """过滤后的工具是同一个引用（不是拷贝）"""
        registry = ToolRegistry()
        tool = _make_tool("read")
        registry.register(tool)

        filtered = registry.filter_by_names(["read"])
        assert filtered.get("read") is registry.get("read")

    def test_filter_does_not_modify_original(self) -> None:
        """过滤不影响原注册表"""
        registry = ToolRegistry()
        registry.register(_make_tool("read"))
        registry.register(_make_tool("write"))

        filtered = registry.filter_by_names(["read"])
        assert len(registry.get_all()) == 2  # 原注册表不变


class TestClone:
    """clone 测试"""

    def test_clone_creates_copy(self) -> None:
        """clone 创建新实例"""
        registry = ToolRegistry()
        registry.register(_make_tool("read"))

        cloned = registry.clone()
        assert cloned is not registry
        assert len(cloned.get_all()) == 1

    def test_clone_shares_tool_references(self) -> None:
        """clone 的工具是同一个引用"""
        registry = ToolRegistry()
        tool = _make_tool("read")
        registry.register(tool)

        cloned = registry.clone()
        assert cloned.get("read") is registry.get("read")

    def test_clone_independent_registration(self) -> None:
        """clone 后注册新工具不影响原注册表"""
        registry = ToolRegistry()
        registry.register(_make_tool("read"))

        cloned = registry.clone()
        cloned.register(_make_tool("write"))

        assert len(registry.get_all()) == 1
        assert len(cloned.get_all()) == 2

    def test_clone_empty_registry(self) -> None:
        """克隆空注册表"""
        registry = ToolRegistry()
        cloned = registry.clone()
        assert len(cloned.get_all()) == 0
