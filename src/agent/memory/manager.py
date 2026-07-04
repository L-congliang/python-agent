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

    # ========== 分层组装 ==========

    def select_relevant_file_summaries(
        self,
        query: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """按相关性选择 file summaries

        规则：recent_files 优先、路径名与 query 关键词重叠、最近访问优先。
        只返回 fresh 的 summaries。

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            [{"path": str, "content": str}, ...]
        """
        recent = set(self._working.get_recent_files())
        query_words = set(query.lower().split())
        results = []

        for path, summary in self._files.get_all().items():
            if not self._files.is_fresh(path):
                continue
            score = 0.0
            # 规则1: recent_files 优先
            if path in recent:
                score += 2.0
            # 规则2: 路径名与 query 关键词重叠
            path_words = set(path.lower().replace("/", " ").replace(".", " ").split())
            overlap = path_words & query_words
            if overlap:
                score += 1.0 * len(overlap)
            results.append({"path": path, "content": summary.content, "score": score})

        # 按 score 降序排列
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def assemble_layered(self, query: str, max_tokens: int = 1600) -> str:
        """分层组装记忆

        顺序：task → recent_files → file_summaries → episodic_notes。
        超出 max_tokens 时从后往前截断。

        Args:
            query: 当前查询（用于 search_notes 和 file_summaries 选择）
            max_tokens: 最大 token 数

        Returns:
            组装后的记忆字符串
        """
        layers: list[str] = []

        # 1. task（总是注入）
        task_str = self._renderer.render_task()
        if task_str:
            layers.append(task_str)

        # 2. recent_files（总是注入）
        files_str = self._renderer.render_recent_files()
        layers.append(files_str)

        # 3. file_summaries（按相关性取 top-k）
        relevant = self.select_relevant_file_summaries(query, top_k=3)
        if relevant:
            summaries_str = self._renderer.render_file_summaries(relevant)
            layers.append(summaries_str)

        # 4. episodic_notes（search_notes 命中后注入）
        if query:
            notes = self.search_notes(query, top_k=3)
            if notes:
                notes_str = self._renderer.render_episodic_notes(notes)
                if notes_str:
                    layers.append(notes_str)

        result = "\n".join(layers)

        # 从后往前截断（先丢 episodic_notes，再丢 file_summaries）
        estimated_tokens = len(result) // 4
        if estimated_tokens > max_tokens:
            target_chars = max_tokens * 4
            result = result[:target_chars]
            # 找最后一个换行符，避免截断中间行
            last_newline = result.rfind("\n")
            if last_newline > 0:
                result = result[:last_newline]

        return result

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
