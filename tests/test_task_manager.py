"""TaskManager 测试"""

import threading
import time

import pytest

from agent.orchestration.message_bus import TaskManager
from agent.orchestration.sub_agent import SubAgentTask, SubAgentResult, SubAgentStatus


class TestTaskManager:
    """TaskManager 测试"""

    def test_register_returns_task_id(self) -> None:
        """注册任务返回 task_id"""
        manager = TaskManager()
        task = SubAgentTask()
        task_id = manager.register(task)
        assert task_id.startswith("sa_")

    def test_get_status_running(self) -> None:
        """查询运行中的任务状态"""
        manager = TaskManager()
        task = SubAgentTask()
        manager.register(task)
        assert manager.get_status(task.task_id) == "running"

    def test_get_status_nonexistent(self) -> None:
        """查询不存在的任务"""
        manager = TaskManager()
        with pytest.raises(KeyError):
            manager.get_status("nonexistent")

    def test_get_result_completed(self) -> None:
        """获取已完成任务的结果"""
        manager = TaskManager()
        task = SubAgentTask()
        task.result = SubAgentResult(
            result="Found 5 TODOs",
            status=SubAgentStatus.COMPLETED,
        )
        task.status = SubAgentStatus.COMPLETED
        manager.register(task)

        result = manager.get_result(task.task_id)
        assert result.result == "Found 5 TODOs"
        assert result.status == SubAgentStatus.COMPLETED

    def test_get_result_blocks_until_complete(self) -> None:
        """get_result 阻塞等待任务完成"""
        manager = TaskManager()
        task = SubAgentTask()

        def complete_later() -> None:
            time.sleep(0.1)
            task.result = SubAgentResult(
                result="Done",
                status=SubAgentStatus.COMPLETED,
            )
            task.status = SubAgentStatus.COMPLETED

        thread = threading.Thread(target=complete_later)
        task.thread = thread
        manager.register(task)
        thread.start()

        result = manager.get_result(task.task_id)
        assert result.result == "Done"
        thread.join()

    def test_stop(self) -> None:
        """停止任务"""
        manager = TaskManager()
        task = SubAgentTask()
        manager.register(task)

        assert not task.abort_flag.is_set()
        manager.stop(task.task_id)
        assert task.abort_flag.is_set()

    def test_stop_nonexistent(self) -> None:
        """停止不存在的任务"""
        manager = TaskManager()
        with pytest.raises(KeyError):
            manager.stop("nonexistent")

    def test_list_tasks(self) -> None:
        """列出所有任务"""
        manager = TaskManager()
        task1 = SubAgentTask()
        task2 = SubAgentTask()
        manager.register(task1)
        manager.register(task2)

        tasks = manager.list_tasks()
        assert len(tasks) == 2
        task_ids = {t["task_id"] for t in tasks}
        assert task1.task_id in task_ids
        assert task2.task_id in task_ids

    def test_cleanup(self) -> None:
        """清理已完成的任务"""
        manager = TaskManager()
        task1 = SubAgentTask()
        task1.status = SubAgentStatus.COMPLETED
        task2 = SubAgentTask()
        task2.status = SubAgentStatus.RUNNING

        manager.register(task1)
        manager.register(task2)

        manager.cleanup()

        tasks = manager.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == task2.task_id

    def test_concurrent_access(self) -> None:
        """并发访问测试"""
        manager = TaskManager()
        tasks = [SubAgentTask() for _ in range(10)]

        # 并发注册
        threads = []
        for task in tasks:
            t = threading.Thread(target=manager.register, args=(task,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(manager.list_tasks()) == 10
