"""Tests for ReflectionBuilder — 预算受控的反思 prompt 构造 + ReflectionPlan 输出"""

from __future__ import annotations

import pytest

from agent.reflection.types import ReflectionConfig, ReflectionPlan, ReflectionSummary
from agent.reflection.builder import ReflectionBuilder


# ============================================================
# 辅助构造
# ============================================================


def _make_summary(
    task_id: str = "test_task",
    first_attempt_correct: bool = False,
    tool_calls: int = 1,
    read_target_after_setup: bool = False,
    memory_hit: int = 0,
    failure_reason: str = "wrong answer",
    tool_trajectory_summary: str = "read(test.py) -> answer",
    memory_summary: str = "setup info: use 4 spaces",
) -> ReflectionSummary:
    return ReflectionSummary(
        task_id=task_id,
        original_prompt="What is the config value?",
        first_attempt_correct=first_attempt_correct,
        first_attempt_answer_preview="wrong answer",
        tool_calls=tool_calls,
        read_target_after_setup=read_target_after_setup,
        memory_hit=memory_hit,
        failure_reason=failure_reason,
        tool_trajectory_summary=tool_trajectory_summary,
        memory_summary=memory_summary,
    )


# ============================================================
# Tests: 基本功能（ReflectionPlan 输出）
# ============================================================


class TestReflectionBuilder:
    """ReflectionBuilder 基本功能"""

    def test_build_returns_reflection_plan(self) -> None:
        """build() 返回 ReflectionPlan"""
        config = ReflectionConfig(enabled=True)
        builder = ReflectionBuilder(config)
        summary = _make_summary()

        plan = builder.build(summary)

        assert isinstance(plan, ReflectionPlan)
        assert isinstance(plan.prompt, str)
        assert len(plan.prompt) > 0
        assert isinstance(plan.retry_strategy, str)
        assert isinstance(plan.should_reread_target, bool)

    def test_build_prompt_contains_failure_info(self) -> None:
        """plan.prompt 包含失败信息"""
        config = ReflectionConfig(enabled=True)
        builder = ReflectionBuilder(config)
        summary = _make_summary(
            failure_reason="wrong answer",
            read_target_after_setup=True,
        )

        plan = builder.build(summary)

        assert "wrong answer" in plan.prompt or "incorrect" in plan.prompt.lower()

    def test_build_prompt_contains_task_id(self) -> None:
        """plan.prompt 包含 task_id"""
        config = ReflectionConfig(enabled=True)
        builder = ReflectionBuilder(config)
        summary = _make_summary(task_id="my_special_task")

        plan = builder.build(summary)

        assert "my_special_task" in plan.prompt

    def test_build_prompt_contains_retry_strategy(self) -> None:
        """plan.prompt 包含 retry_strategy 行"""
        config = ReflectionConfig(enabled=True)
        builder = ReflectionBuilder(config)
        summary = _make_summary(read_target_after_setup=True)

        plan = builder.build(summary)

        assert "retry_strategy:" in plan.prompt


# ============================================================
# Tests: retry_strategy 选择逻辑
# ============================================================


class TestRetryStrategySelection:
    """retry_strategy 根据触发类型选择"""

    def test_reread_triggers_use_memory_strategy(self) -> None:
        """reread 触发时 → use_memory_answer（不 reread）"""
        config = ReflectionConfig(enabled=True)
        builder = ReflectionBuilder(config)
        summary = _make_summary(
            first_attempt_correct=True,
            read_target_after_setup=True,
        )

        plan = builder.build(summary)

        assert plan.retry_strategy == "use_memory_answer"
        assert plan.should_reread_target is False

    def test_incorrect_without_reread_triggers_reread_strategy(self) -> None:
        """答错且没 reread → reread_then_answer"""
        config = ReflectionConfig(enabled=True)
        builder = ReflectionBuilder(config)
        summary = _make_summary(
            first_attempt_correct=False,
            read_target_after_setup=False,
        )

        plan = builder.build(summary)

        assert plan.retry_strategy == "reread_then_answer"
        assert plan.should_reread_target is True

    def test_default_is_use_memory(self) -> None:
        """默认 → use_memory_answer"""
        config = ReflectionConfig(enabled=True)
        builder = ReflectionBuilder(config)
        summary = _make_summary(
            first_attempt_correct=True,
            read_target_after_setup=False,
        )

        plan = builder.build(summary)

        assert plan.retry_strategy == "use_memory_answer"
        assert plan.should_reread_target is False


# ============================================================
# Tests: 长度受控
# ============================================================


class TestReflectionBuilderBudget:
    """reflection prompt 长度受控"""

    def test_build_respects_max_tokens(self) -> None:
        """build() 输出长度受控"""
        config = ReflectionConfig(enabled=True, reflection_max_tokens=200)
        builder = ReflectionBuilder(config)
        summary = _make_summary(
            tool_trajectory_summary="a" * 500,
            memory_summary="b" * 500,
        )

        plan = builder.build(summary)

        max_chars = config.reflection_max_tokens * 4
        assert len(plan.prompt) <= max_chars + 50

    def test_build_truncates_long_inputs(self) -> None:
        """build() 对过长输入进行截断"""
        config = ReflectionConfig(enabled=True, reflection_max_tokens=100)
        builder = ReflectionBuilder(config)
        summary = _make_summary(
            tool_trajectory_summary="x" * 10000,
            memory_summary="y" * 10000,
        )

        plan = builder.build(summary)

        max_chars = config.reflection_max_tokens * 4
        assert len(plan.prompt) <= max_chars + 50


# ============================================================
# Tests: 降级工作
# ============================================================


class TestReflectionBuilderDegradation:
    """缺少字段时能降级工作"""

    def test_build_with_empty_tool_trajectory(self) -> None:
        config = ReflectionConfig(enabled=True)
        builder = ReflectionBuilder(config)
        summary = _make_summary(tool_trajectory_summary="")

        plan = builder.build(summary)

        assert isinstance(plan, ReflectionPlan)
        assert len(plan.prompt) > 0

    def test_build_with_empty_memory_summary(self) -> None:
        config = ReflectionConfig(enabled=True)
        builder = ReflectionBuilder(config)
        summary = _make_summary(memory_summary="")

        plan = builder.build(summary)

        assert isinstance(plan, ReflectionPlan)
        assert len(plan.prompt) > 0

    def test_build_with_empty_failure_reason(self) -> None:
        config = ReflectionConfig(enabled=True)
        builder = ReflectionBuilder(config)
        summary = _make_summary(failure_reason="", first_attempt_correct=True)

        plan = builder.build(summary)

        assert isinstance(plan, ReflectionPlan)
        assert len(plan.prompt) > 0

    def test_build_with_all_empty(self) -> None:
        config = ReflectionConfig(enabled=True)
        builder = ReflectionBuilder(config)
        summary = ReflectionSummary(
            task_id="empty_task",
            original_prompt="test",
            first_attempt_correct=False,
        )

        plan = builder.build(summary)

        assert isinstance(plan, ReflectionPlan)
        assert len(plan.prompt) > 0
