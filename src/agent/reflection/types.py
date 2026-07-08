"""Reflection 数据结构

Phase 3.2C: Controlled Reflection - Bounded Self-Correction

独立于 LoopConfig 的 reflection 配置和判定结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReflectionConfig:
    """Reflection 配置（独立于 LoopConfig）

    Attributes:
        enabled: 是否启用 reflection
        max_reflections_per_task: 每任务最多 reflection 次数（默认 1）
        only_on_failure: 是否只在失败时触发
        enable_on_reread: 是否在 reread 时触发
        enable_on_high_tool_calls: 是否在 tool_calls 超阈值时触发
        tool_call_threshold: tool_calls 阈值
        reflection_max_tokens: reflection prompt 最大 token 数
    """
    enabled: bool = False
    max_reflections_per_task: int = 1
    only_on_failure: bool = True
    enable_on_reread: bool = True
    enable_on_high_tool_calls: bool = True
    tool_call_threshold: int = 5
    reflection_max_tokens: int = 1024


@dataclass
class ReflectionDecision:
    """是否触发 reflection 的判定结果

    Attributes:
        should_reflect: 是否应该触发 reflection
        reason: 触发原因描述
        trigger_type: 触发类型（incorrect / reread / high_tool_calls / none）
    """
    should_reflect: bool
    reason: str
    trigger_type: str = "none"  # "incorrect" | "reread" | "high_tool_calls" | "none"


@dataclass
class ReflectionSummary:
    """反思输入摘要

    用于 ReflectionBuilder 构造反思 prompt 的输入。
    只包含摘要信息，不包含全量 messages / tool results。

    Attributes:
        task_id: 任务 ID
        original_prompt: 原任务 prompt
        first_attempt_correct: 第一次是否正确
        first_attempt_answer_preview: 第一次回答预览
        tool_calls: 第一次 tool calls 数量
        read_target_after_setup: 是否 reread 了目标文件
        memory_hit: memory hit 状态（1=命中, 0=未命中, -1=不适用）
        failure_reason: 失败原因
        tool_trajectory_summary: 工具调用摘要
        memory_summary: 当前 memory 摘要
    """
    task_id: str
    original_prompt: str
    first_attempt_correct: bool
    first_attempt_answer_preview: str = ""
    tool_calls: int = 0
    read_target_after_setup: bool = False
    memory_hit: int = -1
    failure_reason: str = ""
    tool_trajectory_summary: str = ""
    memory_summary: str = ""


@dataclass
class ReflectionPlan:
    """ReflectionBuilder 的结构化输出

    分离"给模型的文本"和"给 harness 的控制信号"。
    prompt 给模型/agent，retry_strategy 给 benchmark harness 做 branch routing。

    Attributes:
        prompt: 给模型/agent 的反思文本
        retry_strategy: 给 benchmark harness 的 routing 信号
        should_reread_target: 是否应该 reread 目标文件
    """
    prompt: str
    retry_strategy: str = "use_memory_answer"
    should_reread_target: bool = False
