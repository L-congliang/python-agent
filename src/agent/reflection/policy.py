"""Reflection Policy — 判定是否触发 reflection

三个触发条件（满足任一即触发）：
1. incorrect: 第一次答错（verifier 返回 False）
2. read_target_after_setup: 不必要 reread
3. high_tool_calls: tool_calls 超过阈值
"""

from __future__ import annotations

from typing import Any

from agent.evaluation.memory_experiment import MemoryTask
from agent.reflection.types import ReflectionConfig, ReflectionDecision


class ReflectionPolicy:
    """判定是否触发 reflection

    用法:
        policy = ReflectionPolicy(ReflectionConfig(enabled=True))
        decision = policy.should_reflect(task, first_result)
        if decision.should_reflect:
            # 触发 reflection
    """

    def __init__(self, config: ReflectionConfig) -> None:
        self._config = config

    def should_reflect(
        self,
        task: MemoryTask,
        first_result: dict[str, Any],
    ) -> ReflectionDecision:
        """判定是否触发 reflection

        Args:
            task: 任务定义
            first_result: 第一次执行结果（包含 correct, tool_calls, read_target_after_setup 等）

        Returns:
            ReflectionDecision（should_reflect, reason, trigger_type）
        """
        # 未启用 → 不触发
        if not self._config.enabled:
            return ReflectionDecision(
                should_reflect=False,
                reason="reflection disabled",
                trigger_type="none",
            )

        # 没有 setup_turns 的任务不触发 reflection
        # （reflection 的价值在于"setup 后记忆没用好"的纠正）
        if not task.setup_turns:
            return ReflectionDecision(
                should_reflect=False,
                reason="no setup_turns, reflection not applicable",
                trigger_type="none",
            )

        # 触发条件 1: incorrect（always checked when only_on_failure=True）
        if self._config.only_on_failure and not first_result.get("correct", True):
            return ReflectionDecision(
                should_reflect=True,
                reason=f"first attempt incorrect (failed_reason={first_result.get('failed_reason', '')})",
                trigger_type="incorrect",
            )

        # 触发条件 2: read_target_after_setup（独立于 only_on_failure）
        if self._config.enable_on_reread and first_result.get("read_target_after_setup", False):
            return ReflectionDecision(
                should_reflect=True,
                reason="read target file after setup (should have used memory)",
                trigger_type="reread",
            )

        # 触发条件 3: high tool_calls（独立于 only_on_failure）
        if self._config.enable_on_high_tool_calls:
            tool_calls = first_result.get("tool_calls", 0)
            if tool_calls > self._config.tool_call_threshold:
                return ReflectionDecision(
                    should_reflect=True,
                    reason=f"tool_calls ({tool_calls}) exceeds threshold ({self._config.tool_call_threshold})",
                    trigger_type="high_tool_calls",
                )

        # 无触发条件满足
        return ReflectionDecision(
            should_reflect=False,
            reason="no trigger condition met",
            trigger_type="none",
        )
