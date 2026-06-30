"""工作记忆 - 当前 session 的临时信息

设计决策:
- 为什么用 LRU？
  最近访问的文件最可能再次使用
  淘汰最久未访问的文件，保持列表相关性

- 为什么限制 recent_files 为 8 个？
  太少会频繁淘汰，太多会占用 token
  8 个是经验值，覆盖"当前工作区"的典型文件数
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkingMemory:
    """工作记忆

    Attributes:
        task_summary: 当前任务描述
        recent_files: 最近访问文件列表（LRU，最多 8 个）
        extra: 扩展字段
    """
    task_summary: str = ""
    recent_files: OrderedDict[str, None] = field(default_factory=OrderedDict)
    extra: dict[str, Any] = field(default_factory=dict)

    # 常量
    MAX_RECENT_FILES: int = 8

    def set_task_summary(self, summary: str) -> None:
        """设置任务摘要

        Args:
            summary: 任务描述
        """
        self.task_summary = summary

    def touch_file(self, file_path: str) -> None:
        """记录文件访问（LRU 语义）

        如果文件已存在，移到末尾（最近访问）
        如果不存在，添加到末尾
        如果超过 MAX_RECENT_FILES，淘汰最久未访问的

        Args:
            file_path: 文件路径
        """
        # 如果已存在，先移除
        if file_path in self.recent_files:
            del self.recent_files[file_path]

        # 添加到末尾
        self.recent_files[file_path] = None

        # 淘汰多余的
        while len(self.recent_files) > self.MAX_RECENT_FILES:
            self.recent_files.popitem(last=False)

    def get_recent_files(self) -> list[str]:
        """获取最近访问文件列表

        Returns:
            文件路径列表（最近访问的在最后）
        """
        return list(self.recent_files.keys())

    def clear(self) -> None:
        """清空工作记忆"""
        self.task_summary = ""
        self.recent_files.clear()
        self.extra.clear()

    def is_empty(self) -> bool:
        """检查是否为空

        Returns:
            是否为空
        """
        return not self.task_summary and not self.recent_files
