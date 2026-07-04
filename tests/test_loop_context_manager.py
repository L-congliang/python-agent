"""_build_system_prompt ContextManager 集成测试"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.core.loop import AgentLoop, LoopConfig
from agent.core.model import ModelConfig


def _make_loop(memory_enabled: bool = True) -> AgentLoop:
    """创建测试用 AgentLoop"""
    from agent.core.model import MimoClient
    from agent.tools.registry import ToolRegistry
    from agent.tools.bash import bash_tool
    from agent.tools.file_read import file_read_tool
    config = ModelConfig(api_key="test-key", base_url="http://test", model="test")
    client = MagicMock(spec=MimoClient)
    client.config = config
    registry = ToolRegistry()
    registry.register(bash_tool)
    registry.register(file_read_tool)
    loop_config = LoopConfig(memory_enabled=memory_enabled)
    return AgentLoop(client=client, registry=registry, config=loop_config)


class TestBuildSystemPrompt:
    """_build_system_prompt() 集成测试"""

    def test_uses_context_manager(self) -> None:
        """走 ContextManager 路径"""
        loop = _make_loop()
        prompt = loop._build_system_prompt()
        # 应该包含 identity
        assert "Cool Code" in prompt
        # 应该包含行为准则
        assert "行为准则" in prompt

    def test_contains_tools(self) -> None:
        """包含工具列表"""
        loop = _make_loop()
        prompt = loop._build_system_prompt()
        assert "可用工具:" in prompt

    def test_memory_disabled(self) -> None:
        """memory_enabled=False 时 memory 为空"""
        loop = _make_loop(memory_enabled=False)
        prompt = loop._build_system_prompt()
        # 不应包含 task: （memory section 的标志）
        lines = prompt.split("\n")
        memory_lines = [l for l in lines if l.strip().startswith("task:")]
        assert len(memory_lines) == 0

    def test_context_metadata_set(self) -> None:
        """_last_context_metadata 被正确设置"""
        loop = _make_loop()
        loop._build_system_prompt()
        assert loop._last_context_metadata is not None
        assert loop._last_context_metadata.total_rendered_tokens > 0

    def test_with_memory(self) -> None:
        """启用 memory 时包含记忆内容"""
        loop = _make_loop(memory_enabled=True)
        loop._memory.set_task("fix the bug")
        prompt = loop._build_system_prompt()
        assert "fix the bug" in prompt
