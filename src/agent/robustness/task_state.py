"""
TaskState 状态机 - 追踪任务状态流转

状态流转:
- running → completed (模型返回 final answer)
- running → stopped (达到步数/重试限制)
- running → failed (模型 API 错误)

设计决策:
- 为什么用 Enum？状态有限且固定，Enum 提供类型安全
- 为什么单独一个类？状态逻辑复杂，分离关注点
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    """任务状态"""
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class StopReason(Enum):
    """停止原因"""
    NONE = "none"
    FINAL_ANSWER = "final_answer_returned"
    STEP_LIMIT = "step_limit_reached"
    RETRY_LIMIT = "retry_limit_reached"
    MODEL_ERROR = "model_error"
    USER_ABORT = "user_abort"
    TOOL_ERROR = "tool_error"


@dataclass
class TaskState:
    """任务状态机

    追踪任务的完整生命周期：
    - run_id: 本次运行的唯一标识
    - task_id: 任务标识（可选）
    - user_request: 用户请求
    - status: 当前状态
    - tool_steps: 工具执行步数
    - attempts: 尝试次数
    - stop_reason: 停止原因
    - final_answer: 最终答案
    - metadata: 附加信息
    """

    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id: str = ""
    user_request: str = ""
    status: TaskStatus = TaskStatus.RUNNING
    tool_steps: int = 0
    attempts: int = 0
    stop_reason: StopReason = StopReason.NONE
    final_answer: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def complete(self, answer: str) -> None:
        """任务完成"""
        self.status = TaskStatus.COMPLETED
        self.final_answer = answer
        self.stop_reason = StopReason.FINAL_ANSWER

    def stop(self, reason: StopReason) -> None:
        """任务停止（达到限制）"""
        self.status = TaskStatus.STOPPED
        self.stop_reason = reason

    def fail(self, reason: StopReason, error: str = "") -> None:
        """任务失败"""
        self.status = TaskStatus.FAILED
        self.stop_reason = reason
        if error:
            self.metadata["error"] = error

    def increment_tool_steps(self) -> int:
        """增加工具步数，返回新值"""
        self.tool_steps += 1
        return self.tool_steps

    def increment_attempts(self) -> int:
        """增加尝试次数，返回新值"""
        self.attempts += 1
        return self.attempts

    def reset_attempts(self) -> None:
        """重置尝试次数（有效调用后）"""
        self.attempts = 0

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.status == TaskStatus.RUNNING

    @property
    def is_done(self) -> bool:
        """是否已结束（完成/停止/失败）"""
        return self.status != TaskStatus.RUNNING

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "user_request": self.user_request[:200],  # 截断过长请求
            "status": self.status.value,
            "tool_steps": self.tool_steps,
            "attempts": self.attempts,
            "stop_reason": self.stop_reason.value,
            "final_answer": self.final_answer[:500],  # 截断过长答案
            "metadata": self.metadata,
        }
