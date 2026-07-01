"""
重复调用拦截 - 检测同一工具同一参数的连续调用

设计决策:
- 为什么用 hash 而不是直接比较参数？
  参数可能很大（如文件内容），hash 更高效
- 为什么是连续 3 次？
  太少会误拦截（模型可能在修正），太多会浪费 token
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CallRecord:
    """工具调用记录"""
    tool_name: str
    arguments_hash: str
    arguments: dict[str, Any]


class RepeatDetector:
    """重复调用检测器

    检测同一工具同一参数的连续调用。
    连续 N 次相同调用 → 拦截并返回提示信息。
    """

    def __init__(self, max_repeats: int = 3) -> None:
        """初始化

        Args:
            max_repeats: 最大连续重复次数（默认 3）
        """
        self._max_repeats = max_repeats
        self._recent_calls: deque[CallRecord] = deque(maxlen=max_repeats)
        self._repeat_count: int = 0
        self._last_hash: str = ""

    def check(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        """检查是否是重复调用

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            (is_repeated, message)
            - is_repeated: 是否是重复调用
            - message: 提示信息（如果是重复）
        """
        # 计算参数 hash
        args_str = json.dumps(arguments, sort_keys=True)
        args_hash = hashlib.md5(f"{tool_name}:{args_str}".encode()).hexdigest()

        # 检查是否与上次相同
        if args_hash == self._last_hash:
            self._repeat_count += 1
        else:
            self._repeat_count = 1
            self._last_hash = args_hash

        # 记录调用
        self._recent_calls.append(CallRecord(
            tool_name=tool_name,
            arguments_hash=args_hash,
            arguments=arguments,
        ))

        # 检查是否超过阈值
        if self._repeat_count >= self._max_repeats:
            # 格式化参数摘要
            args_summary = self._format_args(arguments)
            return True, (
                f"You've called {tool_name}({args_summary}) "
                f"{self._repeat_count} times consecutively. "
                f"Try a different approach or provide a different answer."
            )

        return False, ""

    def reset(self) -> None:
        """重置检测器"""
        self._recent_calls.clear()
        self._repeat_count = 0
        self._last_hash = ""

    @property
    def repeat_count(self) -> int:
        """当前连续重复次数"""
        return self._repeat_count

    def _format_args(self, arguments: dict[str, Any]) -> str:
        """格式化参数为简短摘要"""
        parts = []
        for key, value in arguments.items():
            value_str = str(value)
            if len(value_str) > 50:
                value_str = value_str[:50] + "..."
            parts.append(f"{key}={value_str}")
        return ", ".join(parts)
