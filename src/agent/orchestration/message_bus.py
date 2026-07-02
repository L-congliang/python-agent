"""TaskManager - 后台任务管理

设计决策:
- 为什么用线程而不是 asyncio？
  项目目前是同步的，引入 asyncio 改动太大。
  线程足够简单，TaskManager 用 Lock 保证线程安全。

- 为什么不直接返回结果？
  后台模式需要非阻塞。主 Agent 可以并行派生多个子 Agent。
  TaskManager 通过 task_id 追踪所有后台任务。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from agent.orchestration.sub_agent import SubAgentTask, SubAgentResult, SubAgentStatus

logger = logging.getLogger("agent.orchestration.message_bus")


class TaskManager:
    """后台任务管理器

    管理所有后台执行的子 Agent 任务。
    线程安全：所有操作都通过 Lock 保护。

    使用方式:
        manager = TaskManager()
        task_id = manager.register(task)
        status = manager.get_status(task_id)
        result = manager.get_result(task_id)  # 阻塞等待
        manager.stop(task_id)
    """

    def __init__(self) -> None:
        self._tasks: dict[str, SubAgentTask] = {}
        self._lock = threading.Lock()

    def register(self, task: SubAgentTask) -> str:
        """注册后台任务

        Args:
            task: 子 Agent 任务

        Returns:
            task_id
        """
        with self._lock:
            self._tasks[task.task_id] = task
            logger.info("Registered background task: %s", task.task_id)
            return task.task_id

    def get_status(self, task_id: str) -> str:
        """获取任务状态

        Args:
            task_id: 任务 ID

        Returns:
            状态字符串："running" | "completed" | "stopped" | "failed"

        Raises:
            KeyError: task_id 不存在
        """
        with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"任务 '{task_id}' 不存在")
            return self._tasks[task_id].status.value

    def get_result(self, task_id: str) -> SubAgentResult:
        """获取任务结果（阻塞等待完成）

        Args:
            task_id: 任务 ID

        Returns:
            SubAgentResult

        Raises:
            KeyError: task_id 不存在
        """
        with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"任务 '{task_id}' 不存在")
            task = self._tasks[task_id]

        # 在锁外等待线程完成
        if task.thread is not None:
            task.thread.join()

        return task.result or SubAgentResult(
            status=SubAgentStatus.FAILED,
            error="No result available",
        )

    def stop(self, task_id: str) -> None:
        """停止后台任务

        Args:
            task_id: 任务 ID

        Raises:
            KeyError: task_id 不存在
        """
        with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"任务 '{task_id}' 不存在")
            task = self._tasks[task_id]

        # 请求中断
        task.abort()
        logger.info("Requested stop for task: %s", task_id)

    def list_tasks(self) -> list[dict[str, Any]]:
        """列出所有任务

        Returns:
            任务信息列表
        """
        with self._lock:
            return [
                {
                    "task_id": task.task_id,
                    "status": task.status.value,
                    "has_result": task.result is not None,
                }
                for task in self._tasks.values()
            ]

    def cleanup(self) -> None:
        """清理已完成的任务"""
        with self._lock:
            completed = [
                task_id
                for task_id, task in self._tasks.items()
                if task.status != SubAgentStatus.RUNNING
            ]
            for task_id in completed:
                del self._tasks[task_id]
            if completed:
                logger.info("Cleaned up %d completed tasks", len(completed))
