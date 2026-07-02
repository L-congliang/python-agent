"""子 Agent 数据结构测试"""

import pytest

from agent.orchestration.sub_agent import (
    SubAgentConstraints,
    SubAgentResult,
    SubAgentStatus,
    SubAgentTask,
)


class TestSubAgentConstraints:
    """SubAgentConstraints 测试"""

    def test_initial_state(self) -> None:
        """初始状态"""
        c = SubAgentConstraints()
        assert c.token_budget is None
        assert c.tokens_spent == 0
        assert c.agent_counter == 0
        assert c.max_agents == 100

    def test_remaining_budget_unlimited(self) -> None:
        """不限制预算时返回大数"""
        c = SubAgentConstraints()
        assert c.remaining_budget() == 999_999_999

    def test_remaining_budget_limited(self) -> None:
        """有限预算"""
        c = SubAgentConstraints(token_budget=1000, tokens_spent=300)
        assert c.remaining_budget() == 700

    def test_remaining_budget_exhausted(self) -> None:
        """预算耗尽"""
        c = SubAgentConstraints(token_budget=1000, tokens_spent=1000)
        assert c.remaining_budget() == 0

    def test_remaining_budget_over_spent(self) -> None:
        """超支时返回 0（不返回负数）"""
        c = SubAgentConstraints(token_budget=1000, tokens_spent=1500)
        assert c.remaining_budget() == 0

    def test_can_create_agent(self) -> None:
        """可以创建 agent"""
        c = SubAgentConstraints()
        assert c.can_create_agent() is True

    def test_can_create_agent_at_limit(self) -> None:
        """达到上限时不能创建"""
        c = SubAgentConstraints(agent_counter=100, max_agents=100)
        assert c.can_create_agent() is False

    def test_record_agent_created(self) -> None:
        """记录 agent 创建"""
        c = SubAgentConstraints()
        c.record_agent_created()
        assert c.agent_counter == 1
        c.record_agent_created()
        assert c.agent_counter == 2

    def test_record_tokens_spent(self) -> None:
        """记录 token 消耗"""
        c = SubAgentConstraints()
        c.record_tokens_spent(100)
        assert c.tokens_spent == 100
        c.record_tokens_spent(200)
        assert c.tokens_spent == 300

    def test_shared_constraints(self) -> None:
        """父子 Agent 共享约束"""
        parent_constraints = SubAgentConstraints(token_budget=1000)
        # 子 Agent 持有同一个引用
        child_constraints = parent_constraints
        child_constraints.record_tokens_spent(500)
        # 父 Agent 看到消耗
        assert parent_constraints.tokens_spent == 500
        assert parent_constraints.remaining_budget() == 500


class TestSubAgentResult:
    """SubAgentResult 测试"""

    def test_default_values(self) -> None:
        """默认值"""
        r = SubAgentResult()
        assert r.result == ""
        assert r.status == SubAgentStatus.COMPLETED
        assert r.turns_used == 0
        assert r.error is None

    def test_to_dict(self) -> None:
        """转换为字典"""
        r = SubAgentResult(
            result="Found 5 TODOs",
            status=SubAgentStatus.COMPLETED,
            turns_used=3,
            tool_calls_used=5,
            tokens_used=1000,
            agent_type="explore",
        )
        d = r.to_dict()
        assert d["result"] == "Found 5 TODOs"
        assert d["status"] == "completed"
        assert d["turns_used"] == 3
        assert d["tool_calls_used"] == 5
        assert d["tokens_used"] == 1000
        assert d["agent_type"] == "explore"
        assert d["error"] is None

    def test_to_dict_with_error(self) -> None:
        """带错误的字典转换"""
        r = SubAgentResult(
            status=SubAgentStatus.FAILED,
            error="Model API error",
        )
        d = r.to_dict()
        assert d["status"] == "failed"
        assert d["error"] == "Model API error"


class TestSubAgentStatus:
    """SubAgentStatus 枚举测试"""

    def test_values(self) -> None:
        """枚举值"""
        assert SubAgentStatus.RUNNING.value == "running"
        assert SubAgentStatus.COMPLETED.value == "completed"
        assert SubAgentStatus.STOPPED.value == "stopped"
        assert SubAgentStatus.FAILED.value == "failed"


class TestSubAgentTask:
    """SubAgentTask 测试"""

    def test_default_values(self) -> None:
        """默认值"""
        task = SubAgentTask()
        assert task.task_id.startswith("sa_")
        assert task.thread is None
        assert task.status == SubAgentStatus.RUNNING
        assert task.result is None
        assert not task.abort_flag.is_set()

    def test_custom_task_id(self) -> None:
        """自定义 task_id"""
        task = SubAgentTask(task_id="sa_custom")
        assert task.task_id == "sa_custom"

    def test_abort(self) -> None:
        """abort 设置标志"""
        task = SubAgentTask()
        assert not task.abort_flag.is_set()
        task.abort()
        assert task.abort_flag.is_set()

    def test_unique_ids(self) -> None:
        """每次生成唯一的 task_id"""
        tasks = [SubAgentTask() for _ in range(10)]
        ids = {t.task_id for t in tasks}
        assert len(ids) == 10
