"""事件笔记 - 带时间戳和标签的事件记录

设计决策:
- 为什么限制 500 字符？
  笔记应该是简洁的，不是完整的对话记录
  500 字符足够记录关键信息

- 为什么限制 12 条？
  太多会占用 token，太少会丢失重要信息
  12 条是经验值，覆盖一个典型 session 的关键事件

- 为什么需要去重？
  避免重复记录相同事件
  用 text 精确匹配，简单高效

- 为什么需要 source？
  追踪笔记来源，便于调试
  区分用户输入、工具结果、系统事件
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Note:
    """事件笔记

    Attributes:
        text: 笔记内容（最多 500 字符）
        tags: 标签列表
        created_at: 创建时间戳
        source: 来源（user, tool, system）
    """
    text: str
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    source: str = ""

    # 常量
    MAX_TEXT_LENGTH: int = 500

    def __post_init__(self) -> None:
        """初始化后处理"""
        # 截断过长的文本
        if len(self.text) > self.MAX_TEXT_LENGTH:
            self.text = self.text[:self.MAX_TEXT_LENGTH] + "..."

        # 设置默认时间戳
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class EpisodicNotes:
    """事件笔记管理器

    使用方式:
        notes = EpisodicNotes()
        notes.append("发现 bug 在 line 42", tags=["bug"], source="tool")
        recent = notes.get_recent(3)
    """

    def __init__(self, max_notes: int = 12) -> None:
        """初始化

        Args:
            max_notes: 最大笔记数量
        """
        self._notes: list[Note] = []
        self._max_notes = max_notes

    def append(
        self,
        text: str,
        tags: list[str] | None = None,
        source: str = "",
    ) -> Note | None:
        """添加笔记（去重）

        Args:
            text: 笔记内容
            tags: 标签列表
            source: 来源

        Returns:
            添加的 Note，如果重复则返回 None
        """
        # 去重检查
        for existing in self._notes:
            if existing.text == text:
                return None

        # 创建笔记
        note = Note(
            text=text,
            tags=tags or [],
            source=source,
        )

        self._notes.append(note)

        # 淘汰多余的笔记
        while len(self._notes) > self._max_notes:
            self._notes.pop(0)

        return note

    def get_recent(self, count: int = 3) -> list[Note]:
        """获取最近的笔记

        Args:
            count: 获取数量

        Returns:
            最近的笔记列表
        """
        return self._notes[-count:]

    def get_by_tag(self, tag: str) -> list[Note]:
        """按标签获取笔记

        Args:
            tag: 标签

        Returns:
            带有该标签的笔记列表
        """
        return [n for n in self._notes if tag in n.tags]

    def get_all(self) -> list[Note]:
        """获取所有笔记

        Returns:
            所有笔记列表
        """
        return list(self._notes)

    def clear(self) -> None:
        """清空所有笔记"""
        self._notes.clear()

    def __len__(self) -> int:
        """获取笔记数量"""
        return len(self._notes)

    def __bool__(self) -> bool:
        """检查是否有笔记"""
        return bool(self._notes)
