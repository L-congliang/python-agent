"""
重试上限 - 限制连续无效调用次数

设计决策:
- 为什么区分"无效调用"和"错误调用"？
  无效调用是模型输出格式错误（如 JSON 解析失败），
  错误调用是工具执行失败（如文件不存在）。
  只有无效调用才计入重试上限。
- 为什么有效调用重置计数？
  模型已经恢复正常，之前的无效调用不再相关。
"""

from __future__ import annotations


class RetryLimiter:
    """重试上限限制器

    连续 N 次无效工具调用 → 强制结束。
    有效调用重置计数。
    """

    def __init__(self, max_retries: int = 5) -> None:
        """初始化

        Args:
            max_retries: 最大连续重试次数（默认 5）
        """
        self._max_retries = max_retries
        self._consecutive_failures: int = 0

    def record_failure(self) -> tuple[bool, str]:
        """记录一次无效调用

        Returns:
            (should_stop, message)
            - should_stop: 是否应该停止
            - message: 提示信息（如果应该停止）
        """
        self._consecutive_failures += 1

        if self._consecutive_failures >= self._max_retries:
            return True, (
                f"Too many malformed responses ({self._consecutive_failures}). "
                f"Stopping to prevent infinite loop."
            )

        return False, ""

    def record_success(self) -> None:
        """记录一次有效调用（重置计数）"""
        self._consecutive_failures = 0

    @property
    def consecutive_failures(self) -> int:
        """当前连续失败次数"""
        return self._consecutive_failures

    @property
    def is_exceeded(self) -> bool:
        """是否已超过限制"""
        return self._consecutive_failures >= self._max_retries

    def reset(self) -> None:
        """重置"""
        self._consecutive_failures = 0
