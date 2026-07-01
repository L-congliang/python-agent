"""
工具鲁棒性测试 - Phase 3

测试覆盖:
- TaskState: 状态机流转
- RepeatDetector: 重复调用检测
- PathGuard: 路径逃逸防护
- RetryLimiter: 重试上限
"""

import pytest
from pathlib import Path

from agent.robustness.task_state import TaskState, TaskStatus, StopReason
from agent.robustness.repeat_detector import RepeatDetector
from agent.robustness.path_guard import PathGuard
from agent.robustness.retry_limiter import RetryLimiter


# ============================================================
# TaskState 测试
# ============================================================


class TestTaskState:
    """TaskState 状态机测试"""

    def test_initial_state(self):
        """初始状态应该是 RUNNING"""
        state = TaskState()
        assert state.status == TaskStatus.RUNNING
        assert state.is_running is True
        assert state.is_done is False
        assert state.tool_steps == 0
        assert state.attempts == 0

    def test_complete(self):
        """完成任务应该设置状态为 COMPLETED"""
        state = TaskState()
        state.complete("Hello world")
        assert state.status == TaskStatus.COMPLETED
        assert state.final_answer == "Hello world"
        assert state.stop_reason == StopReason.FINAL_ANSWER
        assert state.is_done is True

    def test_stop(self):
        """停止任务应该设置状态为 STOPPED"""
        state = TaskState()
        state.stop(StopReason.STEP_LIMIT)
        assert state.status == TaskStatus.STOPPED
        assert state.stop_reason == StopReason.STEP_LIMIT
        assert state.is_done is True

    def test_fail(self):
        """失败任务应该设置状态为 FAILED"""
        state = TaskState()
        state.fail(StopReason.MODEL_ERROR, "API timeout")
        assert state.status == TaskStatus.FAILED
        assert state.stop_reason == StopReason.MODEL_ERROR
        assert state.metadata["error"] == "API timeout"
        assert state.is_done is True

    def test_increment_tool_steps(self):
        """增加工具步数应该返回新值"""
        state = TaskState()
        assert state.increment_tool_steps() == 1
        assert state.increment_tool_steps() == 2
        assert state.tool_steps == 2

    def test_increment_attempts(self):
        """增加尝试次数应该返回新值"""
        state = TaskState()
        assert state.increment_attempts() == 1
        assert state.increment_attempts() == 2
        assert state.attempts == 2

    def test_reset_attempts(self):
        """重置尝试次数应该归零"""
        state = TaskState()
        state.increment_attempts()
        state.increment_attempts()
        state.reset_attempts()
        assert state.attempts == 0

    def test_to_dict(self):
        """序列化应该包含所有必要字段"""
        state = TaskState(user_request="test request")
        state.increment_tool_steps()
        d = state.to_dict()
        assert "run_id" in d
        assert d["user_request"] == "test request"
        assert d["status"] == "running"
        assert d["tool_steps"] == 1


# ============================================================
# RepeatDetector 测试
# ============================================================


class TestRepeatDetector:
    """重复调用检测测试"""

    def test_no_repeat(self):
        """不同参数不算重复"""
        detector = RepeatDetector(max_repeats=3)
        is_rep, msg = detector.check("read_file", {"path": "a.py"})
        assert is_rep is False
        is_rep, msg = detector.check("read_file", {"path": "b.py"})
        assert is_rep is False

    def test_repeat_detected(self):
        """连续 3 次相同调用应该被拦截"""
        detector = RepeatDetector(max_repeats=3)
        detector.check("read_file", {"path": "a.py"})
        detector.check("read_file", {"path": "a.py"})
        is_rep, msg = detector.check("read_file", {"path": "a.py"})
        assert is_rep is True
        assert "3 times" in msg

    def test_different_tools_not_repeat(self):
        """不同工具不算重复"""
        detector = RepeatDetector(max_repeats=3)
        detector.check("read_file", {"path": "a.py"})
        detector.check("write_file", {"path": "a.py"})
        is_rep, msg = detector.check("edit_file", {"path": "a.py"})
        assert is_rep is False

    def test_reset(self):
        """重置应该清空计数"""
        detector = RepeatDetector(max_repeats=3)
        detector.check("read_file", {"path": "a.py"})
        detector.check("read_file", {"path": "a.py"})
        detector.reset()
        is_rep, msg = detector.check("read_file", {"path": "a.py"})
        assert is_rep is False

    def test_repeat_count(self):
        """重复计数应该正确"""
        detector = RepeatDetector(max_repeats=3)
        assert detector.repeat_count == 0
        detector.check("read_file", {"path": "a.py"})
        assert detector.repeat_count == 1
        detector.check("read_file", {"path": "a.py"})
        assert detector.repeat_count == 2


# ============================================================
# PathGuard 测试
# ============================================================


class TestPathGuard:
    """路径逃逸防护测试"""

    def test_normal_path(self):
        """正常路径应该通过"""
        guard = PathGuard(workspace_root="/workspace")
        is_safe, msg = guard.check_path("src/main.py")
        assert is_safe is True

    def test_path_escape(self):
        """路径逃逸应该被拦截"""
        guard = PathGuard(workspace_root="/workspace")
        is_safe, msg = guard.check_path("../outside.txt")
        assert is_safe is False
        assert "escape" in msg.lower()

    def test_absolute_path_outside(self):
        """工作区外的绝对路径应该被拦截"""
        guard = PathGuard(workspace_root="/workspace")
        is_safe, msg = guard.check_path("/etc/passwd")
        assert is_safe is False

    def test_absolute_path_inside(self):
        """工作区内的绝对路径应该通过"""
        guard = PathGuard(workspace_root="/workspace")
        is_safe, msg = guard.check_path("/workspace/src/main.py")
        assert is_safe is True

    def test_resolve_path_safe(self):
        """安全路径应该返回解析后的路径"""
        guard = PathGuard(workspace_root="/workspace")
        path = guard.resolve_path("src/main.py")
        assert path is not None
        assert "main.py" in str(path)

    def test_resolve_path_unsafe(self):
        """不安全路径应该返回 None"""
        guard = PathGuard(workspace_root="/workspace")
        path = guard.resolve_path("../outside.txt")
        assert path is None


# ============================================================
# RetryLimiter 测试
# ============================================================


class TestRetryLimiter:
    """重试上限测试"""

    def test_no_failure(self):
        """没有失败时不应该停止"""
        limiter = RetryLimiter(max_retries=5)
        assert limiter.is_exceeded is False
        assert limiter.consecutive_failures == 0

    def test_failure_below_limit(self):
        """失败次数低于限制时不应该停止"""
        limiter = RetryLimiter(max_retries=5)
        for _ in range(4):
            should_stop, msg = limiter.record_failure()
            assert should_stop is False
        assert limiter.consecutive_failures == 4

    def test_failure_at_limit(self):
        """失败次数达到限制时应该停止"""
        limiter = RetryLimiter(max_retries=5)
        for _ in range(4):
            limiter.record_failure()
        should_stop, msg = limiter.record_failure()
        assert should_stop is True
        assert "5" in msg

    def test_success_resets_count(self):
        """成功应该重置失败计数"""
        limiter = RetryLimiter(max_retries=5)
        limiter.record_failure()
        limiter.record_failure()
        limiter.record_success()
        assert limiter.consecutive_failures == 0

    def test_reset(self):
        """重置应该清空计数"""
        limiter = RetryLimiter(max_retries=5)
        limiter.record_failure()
        limiter.record_failure()
        limiter.reset()
        assert limiter.consecutive_failures == 0
        assert limiter.is_exceeded is False
