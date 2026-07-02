"""AgentLoop 子 Agent 支持测试"""

import pytest

from agent.core.loop import AgentLoop, LoopConfig
from agent.core.model import MimoClient
from agent.core.adapters.mimo_adapter import MimoAdapter
from agent.tools.registry import ToolRegistry
from agent.tools.base import build_tool
from agent.core.types import ToolResult
from agent.core.context import ToolUseContext
from agent.orchestration.agent_type import AgentTypeDefinition, AgentTypeRegistry
from agent.orchestration.sub_agent import SubAgentConstraints, SubAgentStatus


def _make_tool(name: str) -> object:
    """创建测试工具"""
    return build_tool(
        name=name,
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}},
        execute_fn=lambda input, ctx: ToolResult(output="ok"),
    )


def _make_parent_agent(
    tools: list[str] | None = None,
    max_turns: int = 50,
    enable_subagent: bool = False,
) -> AgentLoop:
    """创建父 Agent"""
    registry = ToolRegistry()
    for name in (tools or ["read", "write", "grep", "glob", "bash"]):
        registry.register(_make_tool(name))

    config = LoopConfig(
        max_turns=max_turns,
        enable_trace=False,
        enable_checkpoint=False,
        enable_subagent=enable_subagent,
    )
    # 用 None 作为 client，因为测试不调用模型
    return AgentLoop(
        client=None,
        registry=registry,
        config=config,
        adapter=MimoAdapter(),
    )


class TestCreateSubAgent:
    """create_sub_agent 工厂方法测试"""

    def test_creates_sub_agent(self) -> None:
        """创建子 Agent"""
        parent = _make_parent_agent()
        type_registry = AgentTypeRegistry()
        explore_type = type_registry.get("explore")
        constraints = SubAgentConstraints()

        sub = AgentLoop.create_sub_agent(
            parent=parent,
            task="Search for TODOs",
            agent_type_def=explore_type,
            constraints=constraints,
        )

        assert sub is not None
        assert sub is not parent

    def test_sub_agent_has_independent_messages(self) -> None:
        """子 Agent 有独立的消息历史"""
        parent = _make_parent_agent()
        parent._messages.append({"role": "user", "content": "hello"})

        type_registry = AgentTypeRegistry()
        explore_type = type_registry.get("explore")
        constraints = SubAgentConstraints()

        sub = AgentLoop.create_sub_agent(
            parent=parent,
            task="Search for TODOs",
            agent_type_def=explore_type,
            constraints=constraints,
        )

        assert len(sub._messages) == 0

    def test_sub_agent_uses_filtered_tools(self) -> None:
        """子 Agent 使用过滤后的工具集"""
        parent = _make_parent_agent(tools=["read", "write", "grep", "glob", "bash"])
        type_registry = AgentTypeRegistry()
        explore_type = type_registry.get("explore")
        constraints = SubAgentConstraints()

        sub = AgentLoop.create_sub_agent(
            parent=parent,
            task="Search for TODOs",
            agent_type_def=explore_type,
            constraints=constraints,
        )

        tool_names = {t.name for t in sub._registry.get_all()}
        # explore 类型允许 read, grep, glob, bash
        assert "read" in tool_names
        assert "grep" in tool_names
        assert "write" not in tool_names

    def test_sub_agent_max_turns_limited_by_parent(self) -> None:
        """子 Agent 的 max_turns 不能超过父 Agent 剩余轮次"""
        parent = _make_parent_agent(max_turns=10)
        parent._turn_count = 8  # 父 Agent 已用 8 轮

        type_registry = AgentTypeRegistry()
        explore_type = type_registry.get("explore")  # 默认 20 轮
        constraints = SubAgentConstraints()

        sub = AgentLoop.create_sub_agent(
            parent=parent,
            task="Search for TODOs",
            agent_type_def=explore_type,
            constraints=constraints,
        )

        # 父 Agent 剩余 2 轮，子 Agent 应该被限制为 2
        assert sub._config.max_turns == 2

    def test_sub_agent_shares_constraints(self) -> None:
        """子 Agent 持有父 Agent 的约束引用"""
        parent = _make_parent_agent()
        type_registry = AgentTypeRegistry()
        explore_type = type_registry.get("explore")
        constraints = SubAgentConstraints()

        sub = AgentLoop.create_sub_agent(
            parent=parent,
            task="Search for TODOs",
            agent_type_def=explore_type,
            constraints=constraints,
        )

        assert sub._subagent_constraints is constraints

    def test_sub_agent_records_creation(self) -> None:
        """创建子 Agent 时记录 agent counter"""
        parent = _make_parent_agent()
        type_registry = AgentTypeRegistry()
        explore_type = type_registry.get("explore")
        constraints = SubAgentConstraints()

        assert constraints.agent_counter == 0
        AgentLoop.create_sub_agent(
            parent=parent,
            task="Search for TODOs",
            agent_type_def=explore_type,
            constraints=constraints,
        )
        assert constraints.agent_counter == 1

    def test_sub_agent_general_purpose_gets_all_tools(self) -> None:
        """general-purpose 类型继承全部工具"""
        parent = _make_parent_agent(tools=["read", "write", "grep"])
        type_registry = AgentTypeRegistry()
        general_type = type_registry.get("general-purpose")
        constraints = SubAgentConstraints()

        sub = AgentLoop.create_sub_agent(
            parent=parent,
            task="Do something",
            agent_type_def=general_type,
            constraints=constraints,
        )

        tool_names = {t.name for t in sub._registry.get_all()}
        # general-purpose 继承父 Agent 的所有工具，加上自动注册的 subagent
        assert "read" in tool_names
        assert "write" in tool_names
        assert "grep" in tool_names


class TestBuildSubagentPrompt:
    """_build_subagent_prompt 测试"""

    def test_includes_type_description(self) -> None:
        """包含类型描述"""
        parent = _make_parent_agent()
        type_registry = AgentTypeRegistry()
        explore_type = type_registry.get("explore")

        prompt = AgentLoop._build_subagent_prompt(
            parent=parent,
            agent_type_def=explore_type,
            task="Search for TODOs",
        )

        assert "explore" in prompt.lower() or "codebase investigation" in prompt.lower()

    def test_includes_parent_memory(self) -> None:
        """包含父 Agent 的记忆"""
        parent = _make_parent_agent()
        parent._memory.set_task("Fix the bug in main.py")

        type_registry = AgentTypeRegistry()
        explore_type = type_registry.get("explore")

        prompt = AgentLoop._build_subagent_prompt(
            parent=parent,
            agent_type_def=explore_type,
            task="Search for TODOs",
        )

        assert "Fix the bug in main.py" in prompt

    def test_includes_extra_context(self) -> None:
        """包含额外上下文"""
        parent = _make_parent_agent()
        type_registry = AgentTypeRegistry()
        explore_type = type_registry.get("explore")

        prompt = AgentLoop._build_subagent_prompt(
            parent=parent,
            agent_type_def=explore_type,
            task="Search for TODOs",
            extra_context="This is a Python project.",
        )

        assert "This is a Python project." in prompt

    def test_includes_tool_list(self) -> None:
        """包含工具列表"""
        parent = _make_parent_agent(tools=["read", "grep"])
        type_registry = AgentTypeRegistry()
        explore_type = type_registry.get("explore")

        prompt = AgentLoop._build_subagent_prompt(
            parent=parent,
            agent_type_def=explore_type,
            task="Search for TODOs",
        )

        assert "read" in prompt
        assert "grep" in prompt


class TestCreateSubagentResult:
    """create_subagent_result 测试"""

    def test_completed_result(self) -> None:
        """完成状态的结果"""
        parent = _make_parent_agent()
        parent._turn_count = 5
        parent._tool_call_count = 10
        parent._total_tokens = 1000
        parent._task_state.complete("Found 5 TODOs")

        result = parent.create_subagent_result("Found 5 TODOs")
        assert result.status == SubAgentStatus.COMPLETED
        assert result.result == "Found 5 TODOs"
        assert result.turns_used == 5
        assert result.tool_calls_used == 10
        assert result.tokens_used == 1000

    def test_stopped_result(self) -> None:
        """停止状态的结果"""
        from agent.robustness.task_state import StopReason

        parent = _make_parent_agent()
        parent._task_state.stop(StopReason.STEP_LIMIT)

        result = parent.create_subagent_result()
        assert result.status == SubAgentStatus.STOPPED

    def test_failed_result(self) -> None:
        """失败状态的结果"""
        from agent.robustness.task_state import StopReason

        parent = _make_parent_agent()
        parent._task_state.fail(StopReason.MODEL_ERROR, "API error")

        result = parent.create_subagent_result()
        assert result.status == SubAgentStatus.FAILED
        assert result.error == "API error"


class TestSubAgentConstraintsInRun:
    """run() 中的子 Agent 约束检查测试"""

    def test_agent_counter_exceeded(self) -> None:
        """超过 agent 数量限制"""
        parent = _make_parent_agent()
        constraints = SubAgentConstraints(agent_counter=100, max_agents=100)
        parent._subagent_constraints = constraints

        result = parent.run("test")
        assert "超过最大 Agent 数量限制" in result

    def test_token_budget_exhausted(self) -> None:
        """Token 预算耗尽"""
        parent = _make_parent_agent()
        constraints = SubAgentConstraints(token_budget=1000, tokens_spent=1000)
        parent._subagent_constraints = constraints

        result = parent.run("test")
        assert "Token 预算已耗尽" in result
