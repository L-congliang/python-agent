"""Tests for ReflectionPolicy — 触发条件判定"""

from __future__ import annotations

import pytest

from agent.reflection.types import ReflectionConfig, ReflectionDecision
from agent.reflection.policy import ReflectionPolicy


# ============================================================
# 辅助构造
# ============================================================


def _make_task(task_id: str = "test_task", setup_turns: list[str] | None = None):
    """构造 MemoryTask 最小实例"""
    from agent.evaluation.memory_experiment import MemoryTask
    if setup_turns is None:
        setup_turns = ["setup info"]
    return MemoryTask(
        task_id=task_id,
        category="test",
        prompt="test prompt",
        setup_turns=setup_turns,
        target_files=["test.py"],
        verifier="contains_text",
        expected_substrings=["answer"],
    )


def _make_result(
    correct: bool = True,
    tool_calls: int = 0,
    read_target_after_setup: bool = False,
    failed_reason: str = "",
) -> dict:
    """构造 first_result 最小实例"""
    return {
        "correct": correct,
        "tool_calls": tool_calls,
        "read_target_after_setup": read_target_after_setup,
        "failed_reason": failed_reason,
    }


# ============================================================
# Tests: disabled 时不触发
# ============================================================


class TestReflectionPolicyDisabled:
    """disabled 时不触发"""

    def test_disabled_never_triggers(self) -> None:
        config = ReflectionConfig(enabled=False)
        policy = ReflectionPolicy(config)
        task = _make_task(setup_turns=["setup"])
        result = _make_result(correct=False)

        decision = policy.should_reflect(task, result)

        assert not decision.should_reflect
        assert decision.trigger_type == "none"


# ============================================================
# Tests: incorrect 触发
# ============================================================


class TestIncorrectTrigger:
    """incorrect 时触发"""

    def test_incorrect_triggers(self) -> None:
        config = ReflectionConfig(enabled=True, only_on_failure=True)
        policy = ReflectionPolicy(config)
        task = _make_task(setup_turns=["setup"])
        result = _make_result(correct=False, failed_reason="wrong answer")

        decision = policy.should_reflect(task, result)

        assert decision.should_reflect
        assert decision.trigger_type == "incorrect"
        assert "incorrect" in decision.reason

    def test_correct_does_not_trigger_on_failure(self) -> None:
        config = ReflectionConfig(enabled=True, only_on_failure=True)
        policy = ReflectionPolicy(config)
        task = _make_task(setup_turns=["setup"])
        result = _make_result(correct=True)

        decision = policy.should_reflect(task, result)

        assert not decision.should_reflect


# ============================================================
# Tests: reread 触发
# ============================================================


class TestRereadTrigger:
    """reread 时触发"""

    def test_reread_triggers(self) -> None:
        config = ReflectionConfig(enabled=True, enable_on_reread=True, only_on_failure=False)
        policy = ReflectionPolicy(config)
        task = _make_task(setup_turns=["setup"])
        result = _make_result(correct=True, read_target_after_setup=True)

        decision = policy.should_reflect(task, result)

        assert decision.should_reflect
        assert decision.trigger_type == "reread"
        assert "read target" in decision.reason

    def test_no_reread_does_not_trigger(self) -> None:
        config = ReflectionConfig(enabled=True, enable_on_reread=True, only_on_failure=False)
        policy = ReflectionPolicy(config)
        task = _make_task(setup_turns=["setup"])
        result = _make_result(correct=True, read_target_after_setup=False)

        decision = policy.should_reflect(task, result)

        assert not decision.should_reflect


# ============================================================
# Tests: high tool_calls 触发
# ============================================================


class TestHighToolCallsTrigger:
    """tool_calls 超阈值时触发"""

    def test_high_tool_calls_triggers(self) -> None:
        config = ReflectionConfig(
            enabled=True, enable_on_high_tool_calls=True,
            tool_call_threshold=5, only_on_failure=False,
        )
        policy = ReflectionPolicy(config)
        task = _make_task(setup_turns=["setup"])
        result = _make_result(correct=True, tool_calls=10)

        decision = policy.should_reflect(task, result)

        assert decision.should_reflect
        assert decision.trigger_type == "high_tool_calls"
        assert "10" in decision.reason

    def test_low_tool_calls_does_not_trigger(self) -> None:
        config = ReflectionConfig(
            enabled=True, enable_on_high_tool_calls=True,
            tool_call_threshold=5, only_on_failure=False,
        )
        policy = ReflectionPolicy(config)
        task = _make_task(setup_turns=["setup"])
        result = _make_result(correct=True, tool_calls=3)

        decision = policy.should_reflect(task, result)

        assert not decision.should_reflect


# ============================================================
# Tests: no setup_turns 不触发
# ============================================================


class TestNoSetupTurns:
    """没有 setup_turns 的任务不触发"""

    def test_no_setup_turns_no_trigger(self) -> None:
        config = ReflectionConfig(enabled=True, only_on_failure=True)
        policy = ReflectionPolicy(config)
        task = _make_task(setup_turns=[])
        result = _make_result(correct=False)

        decision = policy.should_reflect(task, result)

        assert not decision.should_reflect
        assert "no setup_turns" in decision.reason


# ============================================================
# Tests: 多触发器优先级
# ============================================================


class TestMultipleTriggers:
    """多个触发条件满足时，返回第一个匹配的"""

    def test_incorrect_takes_priority_over_reread(self) -> None:
        config = ReflectionConfig(
            enabled=True, only_on_failure=True,
            enable_on_reread=True,
        )
        policy = ReflectionPolicy(config)
        task = _make_task(setup_turns=["setup"])
        result = _make_result(correct=False, read_target_after_setup=True)

        decision = policy.should_reflect(task, result)

        # incorrect 在 reread 之前检查
        assert decision.should_reflect
        assert decision.trigger_type == "incorrect"

    def test_reread_takes_priority_over_high_tool_calls(self) -> None:
        config = ReflectionConfig(
            enabled=True, only_on_failure=False,
            enable_on_reread=True, enable_on_high_tool_calls=True,
            tool_call_threshold=5,
        )
        policy = ReflectionPolicy(config)
        task = _make_task(setup_turns=["setup"])
        result = _make_result(correct=True, read_target_after_setup=True, tool_calls=10)

        decision = policy.should_reflect(task, result)

        # reread 在 high_tool_calls 之前检查
        assert decision.should_reflect
        assert decision.trigger_type == "reread"
