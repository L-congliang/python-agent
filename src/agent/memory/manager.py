"""记忆管理器 - 整合所有记忆组件

设计决策:
- 为什么需要一个统一的管理器？
  简化外部使用，提供统一接口
  协调各组件的交互
  管理生命周期

- 为什么自动保存？
  避免丢失重要信息
  简化使用流程

- 为什么提供 promote_durable？
  工作记忆中的重要信息应该持久化
  晋升机制保证信息不丢失
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent.memory.working import WorkingMemory
from agent.memory.file_summaries import FileSummaries
from agent.memory.episodic import EpisodicNotes
from agent.memory.durable import DurableMemory
from agent.memory.retrieval import Retrieval
from agent.memory.renderer import MemoryRenderer

logger = logging.getLogger("agent.memory.manager")


class MemoryManager:
    """记忆管理器

    使用方式:
        memory = MemoryManager()
        memory.load()

        # 使用记忆
        memory.set_task("修复 bug")
        memory.touch_file("src/main.py")
        memory.append_note("发现 bug 在 line 42", tags=["bug"])

        # 渲染给模型
        output = memory.render()

        # 持久化重要信息
        memory.promote_durable([
            ("project-conventions", "使用 4 空格缩进"),
        ])

        memory.save()
    """

    def __init__(self, memory_dir: str | Path | None = None) -> None:
        """初始化

        Args:
            memory_dir: 记忆目录路径
        """
        self._working = WorkingMemory()
        self._files = FileSummaries()
        self._notes = EpisodicNotes()
        self._durable = DurableMemory(memory_dir)
        self._retrieval = Retrieval(self._notes)
        self._renderer = MemoryRenderer(
            self._working,
            self._files,
            self._notes,
            self._durable,
        )

    def load(self) -> None:
        """加载持久记忆"""
        self._durable.load()
        logger.info("Loaded durable memory: %s topics", len(self._durable.get_all_topics()))

    def save(self) -> None:
        """保存持久记忆"""
        self._durable.save()
        logger.info("Saved durable memory")

    # ========== 工作记忆操作 ==========

    def set_task(self, summary: str) -> None:
        """设置当前任务

        Args:
            summary: 任务描述
        """
        self._working.set_task_summary(summary)

    def touch_file(self, file_path: str) -> None:
        """记录文件访问

        Args:
            file_path: 文件路径
        """
        self._working.touch_file(file_path)

    def get_task(self) -> str:
        """获取当前任务"""
        return self._working.task_summary

    def get_recent_files(self) -> list[str]:
        """获取最近访问文件"""
        return self._working.get_recent_files()

    # ========== 文件摘要操作 ==========

    def update_file_summary(
        self,
        file_path: str,
        content: str,
        file_mtime: float,
        file_size: int,
    ) -> None:
        """更新文件摘要

        Args:
            file_path: 文件路径
            content: 文件内容
            file_mtime: 修改时间
            file_size: 文件大小
        """
        self._files.update(file_path, content, file_mtime, file_size)

    def get_file_summary(self, file_path: str) -> str | None:
        """获取文件摘要（如果有效）

        Args:
            file_path: 文件路径

        Returns:
            摘要内容或 None
        """
        if self._files.is_fresh(file_path):
            summary = self._files.get(file_path)
            return summary.content if summary else None
        return None

    # ========== 事件笔记操作 ==========

    def append_note(
        self,
        text: str,
        tags: list[str] | None = None,
        source: str = "",
    ) -> bool:
        """添加事件笔记

        Args:
            text: 笔记内容
            tags: 标签
            source: 来源

        Returns:
            是否成功添加（False 表示重复）
        """
        note = self._notes.append(text, tags, source)
        return note is not None

    def search_notes(
        self,
        query: str,
        top_k: int = 3,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """搜索相关笔记

        Args:
            query: 查询文本
            top_k: 返回数量
            tags: 标签过滤

        Returns:
            搜索结果列表
        """
        results = self._retrieval.search(query, top_k, tags)
        return [
            {
                "text": r.note.text,
                "tags": r.note.tags,
                "score": r.score,
                "match_type": r.match_type,
            }
            for r in results
        ]

    # ========== 持久记忆操作 ==========

    def promote_durable(
        self,
        items: list[tuple[str, str]],
        source: str = "",
    ) -> None:
        """晋升到持久记忆

        Args:
            items: [(topic, content), ...] 列表
            source: 来源
        """
        for topic, content in items:
            self._durable.add_note(topic, content, source)
        self._durable.save()

    def get_durable_topics(self) -> list[str]:
        """获取持久记忆主题"""
        return self._durable.get_all_topics()

    # ========== 渲染 ==========

    def render(self) -> str:
        """渲染记忆为紧凑格式

        Returns:
            格式化的记忆字符串
        """
        return self._renderer.render()

    def render_compact(self) -> str:
        """渲染为更紧凑的格式

        Returns:
            更紧凑的记忆字符串
        """
        return self._renderer.render_compact()

    # ========== 生命周期 ==========

    def clear_session(self) -> None:
        """清空会话记忆（保留持久记忆）"""
        self._working.clear()
        self._files.clear()
        self._notes.clear()

    def clear_all(self) -> None:
        """清空所有记忆"""
        self.clear_session()
        self._durable.clear()
