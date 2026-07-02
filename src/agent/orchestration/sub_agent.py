"""子 Agent 数据结构 - 约束、结果、任务

设计决策:
- 为什么需要 SubAgentConstraints？
  嵌套子 Agent 时，所有层级共享同一个 token budget 和 abort signal。
  防止子 Agent 无限消耗资源。

- 为什么 SubAgentResult 是结构化而不是纯文本？
  Claude Code 返回纯文本，但丢失了执行元数据。
  结构化结果让主 Agent 能判断子 Agent 的执行质量。

- 为什么需要 SubAgentTask？
  后台执行模式需要一个对象来管理线程和状态。
  TaskManager 通过 SubAgentTask 追踪所有后台任务。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

logger = logging.getLogger("agent.orchestration.sub_agent")


class SubAgentStatus(str, Enum):
    """子 Agent 执行状态"""
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class SubAgentConstraints:
    """子 Agent 共享约束 - 跨层级传递

    所有层级的 Agent 共享同一个 SubAgentConstraints 实例。
    用于防止嵌套子 Agent 无限消耗资源。

    Attributes:
        token_budget: 总 token 预算（None = 不限制）
        tokens_spent: 已消耗的 token 数
        agent_counter: 已创建的 agent 数
        max_agents: 全局 agent 数上限
        abort_controller: 共享的中断控制器
    """

    token_budget: int | None = None
    tokens_spent: int = 0
    agent_counter: int = 0
    max_agents: int = 100
    abort_controller: Any = None  # AbortController，用 Any 避免循环导入

    def remaining_budget(self) -> int:
        """获取剩余 token 预算

        Returns:
            剩余预算数，如果不限制则返回一个大数
        """
        if self.token_budget is None:
            return 999_999_999  # 不限制
        return max(0, self.token_budget - self.tokens_spent)

    def can_create_agent(self) -> bool:
        """检查是否可以创建新的 agent

        Returns:
            是否可以创建
        """
        return self.agent_counter < self.max_agents

    def record_agent_created(self) -> None:
        """记录创建了一个新的 agent"""
        self.agent_counter += 1

    def record_tokens_spent(self, tokens: int) -> None:
        """记录 token 消耗

        Args:
            tokens: 消耗的 token 数
        """
        self.tokens_spent += tokens


@dataclass
class SubAgentResult:
    """子 Agent 执行结果

    Attributes:
        result: 最终回复文本
        status: 完成状态
        turns_used: 实际轮次
        tool_calls_used: 实际工具调用次数
        tokens_used: 消耗的 token
        agent_type: 使用的 agent 类型
        error: 错误信息（如果失败）
    """

    result: str = ""
    status: SubAgentStatus = SubAgentStatus.COMPLETED
    turns_used: int = 0
    tool_calls_used: int = 0
    tokens_used: int = 0
    agent_type: str = "general-purpose"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于 ToolResult）"""
        return {
            "result": self.result,
            "status": self.status.value,
            "turns_used": self.turns_used,
            "tool_calls_used": self.tool_calls_used,
            "tokens_used": self.tokens_used,
            "agent_type": self.agent_type,
            "error": self.error,
        }


@dataclass
class SubAgentTask:
    """后台任务 - 用于 TaskManager 管理

    Attributes:
        task_id: 任务唯一标识
        thread: 执行线程
        status: 任务状态
        result: 执行结果（完成后填充）
        abort_flag: 中断标志
    """

    task_id: str = field(default_factory=lambda: f"sa_{uuid4().hex[:6]}")
    thread: threading.Thread | None = None
    status: SubAgentStatus = SubAgentStatus.RUNNING
    result: SubAgentResult | None = None
    abort_flag: threading.Event = field(default_factory=threading.Event)

    def abort(self) -> None:
        """请求中断任务"""
        self.abort_flag.set()
