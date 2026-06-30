"""持久记忆 - 跨 session 的重要信息

设计决策:
- 为什么按 topic 分类？
  便于检索和管理
  避免所有信息混在一起

- 为什么用 markdown 格式？
  人类可读，便于手动编辑
  支持格式化（标题、列表）

- 为什么存储在 .agent/memory/ 目录？
  对齐 Claude Code 的目录结构
  便于版本控制（.agent 可以加入 .gitignore）
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.memory.durable")


@dataclass
class DurableNote:
    """持久记忆条目

    Attributes:
        content: 笔记内容
        created_at: 创建时间
        source: 来源
    """
    content: str
    created_at: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        """初始化后处理"""
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class DurableMemory:
    """持久记忆管理器

    存储位置: .agent/memory/topics/{topic}.md

    使用方式:
        memory = DurableMemory()
        memory.load()
        memory.add_note("project-conventions", "使用 4 空格缩进")
        memory.save()
    """

    # 预定义的 topic 类型
    TOPICS = [
        "project-conventions",
        "key-decisions",
        "dependency-facts",
        "user-preferences",
    ]

    def __init__(self, memory_dir: str | Path | None = None) -> None:
        """初始化

        Args:
            memory_dir: 记忆目录路径，默认为 .agent/memory
        """
        if memory_dir is None:
            memory_dir = Path.cwd() / ".agent" / "memory"
        self._memory_dir = Path(memory_dir)
        self._topics_dir = self._memory_dir / "topics"

        # 存储结构: topic -> list[DurableNote]
        self._notes: dict[str, list[DurableNote]] = {t: [] for t in self.TOPICS}

    def load(self) -> None:
        """从磁盘加载记忆"""
        if not self._topics_dir.exists():
            return

        for topic_file in self._topics_dir.glob("*.md"):
            topic = topic_file.stem
            if topic not in self._notes:
                self._notes[topic] = []

            try:
                content = topic_file.read_text(encoding="utf-8")
                self._notes[topic] = self._parse_markdown(content)
            except Exception as e:
                logger.warning("Failed to load topic %s: %s", topic, e)

    def save(self) -> None:
        """保存记忆到磁盘"""
        self._topics_dir.mkdir(parents=True, exist_ok=True)

        for topic, notes in self._notes.items():
            if not notes:
                continue

            topic_file = self._topics_dir / f"{topic}.md"
            content = self._to_markdown(topic, notes)

            try:
                topic_file.write_text(content, encoding="utf-8")
            except Exception as e:
                logger.warning("Failed to save topic %s: %s", topic, e)

    def add_note(
        self,
        topic: str,
        content: str,
        source: str = "",
    ) -> DurableNote:
        """添加持久笔记

        Args:
            topic: 主题
            content: 笔记内容
            source: 来源

        Returns:
            添加的 DurableNote
        """
        if topic not in self._notes:
            self._notes[topic] = []

        note = DurableNote(
            content=content,
            source=source,
        )

        self._notes[topic].append(note)
        return note

    def get_notes(self, topic: str) -> list[DurableNote]:
        """获取指定主题的笔记

        Args:
            topic: 主题

        Returns:
            笔记列表
        """
        return self._notes.get(topic, [])

    def get_all_topics(self) -> list[str]:
        """获取所有主题

        Returns:
            主题列表
        """
        return [t for t, notes in self._notes.items() if notes]

    def clear(self) -> None:
        """清空所有记忆"""
        for topic in self._notes:
            self._notes[topic] = []

    def _parse_markdown(self, content: str) -> list[DurableNote]:
        """解析 markdown 格式的笔记

        Args:
            content: markdown 内容

        Returns:
            笔记列表
        """
        notes = []
        current_note = None

        for line in content.split("\n"):
            if line.startswith("- "):
                # 新笔记
                if current_note:
                    notes.append(current_note)
                current_note = DurableNote(content=line[2:])
            elif current_note and line.startswith("  "):
                # 笔记的额外信息
                if line.strip().startswith("created:"):
                    current_note.created_at = line.split(":", 1)[1].strip()
                elif line.strip().startswith("source:"):
                    current_note.source = line.split(":", 1)[1].strip()

        if current_note:
            notes.append(current_note)

        return notes

    def _to_markdown(self, topic: str, notes: list[DurableNote]) -> str:
        """转换为 markdown 格式

        Args:
            topic: 主题
            notes: 笔记列表

        Returns:
            markdown 内容
        """
        lines = [f"# {topic}\n"]

        for note in notes:
            lines.append(f"- {note.content}")
            if note.created_at:
                lines.append(f"  created: {note.created_at}")
            if note.source:
                lines.append(f"  source: {note.source}")

        return "\n".join(lines) + "\n"
