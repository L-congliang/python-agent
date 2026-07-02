"""多 Agent 评测基准测试

定义多 Agent 场景的评测任务，用于验证 SubAgentTool 的正确性和效率。
"""

import pytest

from agent.core.loop import AgentLoop, LoopConfig
from agent.tools.registry import ToolRegistry
from agent.tools.base import build_tool
from agent.core.types import ToolResult
from agent.orchestration.sub_agent import SubAgentConstraints, SubAgentStatus, SubAgentResult
from agent.orchestration.agent_type import AgentTypeRegistry


def _make_tool(name: str) -> object:
    """创建测试工具"""
    return build_tool(
        name=name,
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}},
        execute_fn=lambda input, ctx: ToolResult(output="ok"),
    )


class TestMultiAgentBenchmark:
    """多 Agent 评测任务"""

    def test_subagent_constraint_tracking(self) -> None:
        """子 Agent 约束追踪"""
        constraints = SubAgentConstraints(token_budget=10000)

        # 模拟 token 消耗
        constraints.record_tokens_spent(3000)
        assert constraints.remaining_budget() == 7000

        constraints.record_tokens_spent(5000)
        assert constraints.remaining_budget() == 2000

        # 预算耗尽
        constraints.record_tokens_spent(3000)
        assert constraints.remaining_budget() == 0

    def test_subagent_agent_counter(self) -> None:
        """子 Agent 计数器"""
        constraints = SubAgentConstraints(max_agents=5)

        # 创建 5 个 agent
        for _ in range(5):
            assert constraints.can_create_agent()
            constraints.record_agent_created()

        # 第 6 个应该被拒绝
        assert not constraints.can_create_agent()

    def test_subagent_type_filtering(self) -> None:
        """子 Agent 类型过滤"""
        from agent.tools.subagent import get_type_registry

        type_registry = get_type_registry()

        # explore 类型应该只有读取工具
        explore = type_registry.get("explore")
        assert "read" in explore.allowed_tools
        assert "grep" in explore.allowed_tools
        assert "write" not in explore.allowed_tools

        # code-reviewer 类型应该只有读取工具
        reviewer = type_registry.get("code-reviewer")
        assert "read" in reviewer.allowed_tools
        assert "write" not in reviewer.allowed_tools

        # general-purpose 类型应该没有过滤
        general = type_registry.get("general-purpose")
        assert general.allowed_tools is None

    def test_subagent_result_structure(self) -> None:
        """子 Agent 结果结构"""
        result = SubAgentResult(
            result="Found 5 TODOs",
            status=SubAgentStatus.COMPLETED,
            turns_used=3,
            tool_calls_used=5,
            tokens_used=1000,
            agent_type="explore",
        )

        d = result.to_dict()
        assert d["result"] == "Found 5 TODOs"
        assert d["status"] == "completed"
        assert d["turns_used"] == 3
        assert d["tool_calls_used"] == 5
        assert d["tokens_used"] == 1000
        assert d["agent_type"] == "explore"

    def test_subagent_constraints_shared(self) -> None:
        """子 Agent 约束共享"""
        constraints = SubAgentConstraints(token_budget=10000, max_agents=10)

        # 模拟多个子 Agent 共享约束
        for i in range(3):
            constraints.record_agent_created()
            constraints.record_tokens_spent(1000 * (i + 1))

        assert constraints.agent_counter == 3
        assert constraints.tokens_spent == 6000  # 1000 + 2000 + 3000
        assert constraints.remaining_budget() == 4000

    def test_subagent_abort_signal(self) -> None:
        """子 Agent 中断信号"""
        from agent.core.context import AbortController

        abort_controller = AbortController()
        constraints = SubAgentConstraints(abort_controller=abort_controller)

        # 初始状态
        assert not abort_controller.is_aborted

        # 触发中断
        abort_controller.abort()
        assert abort_controller.is_aborted

    def test_registry_filter_for_subagent(self) -> None:
        """为子 Agent 过滤工具注册表"""
        registry = ToolRegistry()
        for name in ["read", "write", "grep", "glob", "bash"]:
            registry.register(_make_tool(name))

        # 过滤出 explore 类型的工具
        filtered = registry.filter_by_names(["read", "grep", "glob", "bash"])
        tool_names = {t.name for t in filtered.get_all()}

        assert "read" in tool_names
        assert "grep" in tool_names
        assert "glob" in tool_names
        assert "bash" in tool_names
        assert "write" not in tool_names

    def test_registry_clone_for_subagent(self) -> None:
        """为子 Agent 克隆工具注册表"""
        registry = ToolRegistry()
        for name in ["read", "write", "grep"]:
            registry.register(_make_tool(name))

        # 克隆注册表
        cloned = registry.clone()
        cloned.register(_make_tool("subagent"))

        # 原注册表不受影响
        assert len(registry.get_all()) == 3
        assert len(cloned.get_all()) == 4
