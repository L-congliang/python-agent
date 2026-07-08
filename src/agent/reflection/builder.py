"""Reflection Builder — 构造预算受控的反思 prompt

输入：ReflectionSummary（执行轨迹摘要）
输出：ReflectionPlan（结构化反思输出）

设计约束：
- 长度受控（不超过 reflection_max_tokens）
- 不包含全量 messages / tool results
- 缺少字段时能降级工作
- 输出结构化 ReflectionPlan（prompt + retry_strategy + should_reread_target）
"""

from __future__ import annotations

from agent.reflection.types import ReflectionConfig, ReflectionPlan, ReflectionSummary


class ReflectionBuilder:
    """构造预算受控的反思 prompt

    用法:
        builder = ReflectionBuilder(ReflectionConfig(enabled=True))
        plan = builder.build(summary)
        # plan.prompt — 给模型的反思文本
        # plan.retry_strategy — 给 harness 的 routing 信号
    """

    def __init__(self, config: ReflectionConfig) -> None:
        self._config = config

    def build(self, summary: ReflectionSummary) -> ReflectionPlan:
        """构造反思计划

        Args:
            summary: 反思输入摘要

        Returns:
            ReflectionPlan（prompt + retry_strategy + should_reread_target）
        """
        # 确定 retry_strategy 和 should_reread_target
        retry_strategy, should_reread = self._determine_strategy(summary)

        # 构造 prompt 文本
        prompt = self._build_prompt(summary, retry_strategy, should_reread)

        return ReflectionPlan(
            prompt=prompt,
            retry_strategy=retry_strategy,
            should_reread_target=should_reread,
        )

    def _determine_strategy(
        self, summary: ReflectionSummary,
    ) -> tuple[str, bool]:
        """根据触发类型和 task 特征确定 retry strategy

        核心逻辑：
        - reread 后答对 → memory 已足够，纠正为 use_memory（避免浪费）
        - 没 reread 且答错 → memory 不够，纠正为 reread
        - reread 后答错 → memory 和 file 都不行，尝试换策略
        - 没 reread 且答对 → 默认 use_memory

        Returns:
            (retry_strategy, should_reread_target)
        """
        reread = summary.read_target_after_setup
        correct = summary.first_attempt_correct

        if reread and correct:
            # wasted_reread: reread 了但 memory 其实够用 → 纠正为 use_memory
            return "use_memory_answer", False

        if not reread and not correct:
            # wrong_memory: 用 memory 但答错了 → 纠正为 reread
            return "reread_then_answer", True

        if reread and not correct:
            # reread 了还是错 → 尝试用 memory（可能是 verifier 问题）
            return "use_memory_answer", False

        # not reread and correct → 默认
        return "use_memory_answer", False

    def _build_prompt(
        self,
        summary: ReflectionSummary,
        retry_strategy: str,
        should_reread: bool,
    ) -> str:
        """构造反思 prompt 文本"""
        sections: list[str] = []

        # Section 1: Task info
        sections.append(f"Task: {summary.task_id}")
        sections.append(f"Prompt: {summary.original_prompt}")

        # Section 2: First attempt result
        if summary.first_attempt_correct:
            sections.append("First attempt: CORRECT")
        else:
            sections.append("First attempt: INCORRECT")
            if summary.failure_reason:
                sections.append(f"Failure reason: {summary.failure_reason}")

        # Section 3: Tool trajectory
        if summary.tool_calls > 0:
            sections.append(f"Tool calls: {summary.tool_calls}")
        if summary.tool_trajectory_summary:
            traj = self._truncate(summary.tool_trajectory_summary, 500)
            sections.append(f"Tool trajectory: {traj}")

        # Section 4: Memory state
        if summary.read_target_after_setup:
            sections.append("WARNING: Read target file after setup (should have used memory)")
        if summary.memory_hit >= 0:
            hit_str = "YES" if summary.memory_hit == 1 else "NO"
            sections.append(f"Memory hit: {hit_str}")
        if summary.memory_summary:
            mem = self._truncate(summary.memory_summary, 300)
            sections.append(f"Memory content: {mem}")

        # Section 5: Reflection plan（结构化 routing 信息，嵌入 prompt）
        sections.append("")
        sections.append(f"retry_strategy: {retry_strategy}")
        sections.append(f"should_reread_target: {'yes' if should_reread else 'no'}")
        sections.append("")
        sections.append("Please reflect on what went wrong and retry.")
        if should_reread:
            sections.append("You should re-read the target file to get the correct information.")
        else:
            sections.append("You should use your memory to answer directly without re-reading.")

        # 组装
        full_prompt = "\n".join(sections)

        # 截断到预算
        max_chars = self._config.reflection_max_tokens * 4
        if len(full_prompt) > max_chars:
            full_prompt = full_prompt[:max_chars] + "\n... [truncated]"

        return full_prompt

    def _truncate(self, text: str, max_chars: int) -> str:
        """截断文本到指定长度"""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."
