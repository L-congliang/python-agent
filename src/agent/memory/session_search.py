"""Session Search - 跨 session 的记忆检索

设计决策:
- 为什么不用向量数据库？
  当前阶段不需要复杂的 embedding 检索
  结构化检索 + 关键词匹配足够支撑 baseline 对比
  避免引入外部依赖

- 为什么同时搜索 session 和 durable？
  session 包含历史对话的细节
  durable 包含跨 session 的重要事实
  两者互补，提供更完整的上下文

- 为什么限制 top_k？
  避免 recall 无脑灌爆 prompt
  受 budget 控制，和 observation budget 对齐
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.memory.session_search")


@dataclass
class SearchResult:
    """检索结果

    Attributes:
        content: 匹配的内容
        source: 来源类型（session / durable）
        source_id: 来源 ID（session_id 或 topic）
        score: 相关性分数（0-1）
        match_type: 匹配类型（keyword / structure）
    """
    content: str
    source: str
    source_id: str
    score: float
    match_type: str


class SessionSearch:
    """Session 检索器

    检索历史 session 和 durable memory 中的相关信息。

    使用方式:
        search = SessionSearch(session_dir, memory_dir)
        results = search.search("max_turns", top_k=3)
    """

    def __init__(
        self,
        session_dir: Path | str | None = None,
        memory_dir: Path | str | None = None,
    ) -> None:
        """初始化

        Args:
            session_dir: session 目录
            memory_dir: memory 目录
        """
        self._session_dir = Path(session_dir) if session_dir else None
        self._memory_dir = Path(memory_dir) if memory_dir else None

    def search(
        self,
        query: str,
        top_k: int = 3,
    ) -> list[SearchResult]:
        """搜索相关记忆

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            最相关的记忆列表
        """
        results: list[SearchResult] = []

        # 搜索 session
        if self._session_dir and self._session_dir.exists():
            session_results = self._search_sessions(query)
            results.extend(session_results)

        # 搜索 durable memory
        if self._memory_dir and self._memory_dir.exists():
            durable_results = self._search_durable(query)
            results.extend(durable_results)

        # 按分数排序
        results.sort(key=lambda x: x.score, reverse=True)

        return results[:top_k]

    def _search_sessions(self, query: str) -> list[SearchResult]:
        """搜索 session 文件

        Args:
            query: 查询文本

        Returns:
            匹配的 session 结果
        """
        results: list[SearchResult] = []

        if not self._session_dir:
            return results

        query_lower = query.lower()
        query_words = set(query_lower.split())

        for session_file in self._session_dir.glob("session_*.json"):
            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
                session_id = data.get("id", session_file.stem)

                # 搜索消息
                messages = data.get("messages", [])
                for msg in messages:
                    content = msg.get("content", "")
                    if not content:
                        continue

                    content_lower = content.lower()
                    content_words = set(content_lower.split())
                    overlap = query_words & content_words

                    if overlap:
                        score = len(overlap) / len(query_words) * 0.8
                        # 截取匹配片段
                        preview = content[:200] + "..." if len(content) > 200 else content
                        results.append(SearchResult(
                            content=preview,
                            source="session",
                            source_id=session_id,
                            score=score,
                            match_type="keyword",
                        ))
                        break  # 每个 session 只取第一个匹配

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to parse session %s: %s", session_file, e)

        return results

    def _search_durable(self, query: str) -> list[SearchResult]:
        """搜索 durable memory

        Args:
            query: 查询文本

        Returns:
            匹配的 durable 结果
        """
        results: list[SearchResult] = []

        if not self._memory_dir:
            return results

        topics_dir = self._memory_dir / "topics"
        if not topics_dir.exists():
            return results

        query_lower = query.lower()
        query_words = set(query_lower.split())

        for topic_file in topics_dir.glob("*.md"):
            try:
                topic = topic_file.stem
                content = topic_file.read_text(encoding="utf-8")

                # 解析 markdown 内容
                notes = self._parse_markdown_notes(content)
                for note in notes:
                    note_lower = note.lower()
                    # 检查查询词是否出现在笔记中
                    matched_words = []
                    for word in query_words:
                        if word in note_lower:
                            matched_words.append(word)

                    if matched_words:
                        score = len(matched_words) / len(query_words) * 0.9
                        preview = note[:200] + "..." if len(note) > 200 else note
                        results.append(SearchResult(
                            content=preview,
                            source="durable",
                            source_id=topic,
                            score=score,
                            match_type="keyword",
                        ))

            except Exception as e:
                logger.warning("Failed to parse topic %s: %s", topic_file, e)

        return results

    def _parse_markdown_notes(self, content: str) -> list[str]:
        """解析 markdown 内容中的笔记

        Args:
            content: markdown 内容

        Returns:
            笔记列表
        """
        notes: list[str] = []
        current_note: list[str] = []

        for line in content.split("\n"):
            if line.startswith("- "):
                if current_note:
                    notes.append("\n".join(current_note))
                current_note = [line[2:]]  # 去掉 "- " 前缀
            elif current_note and line.strip():
                current_note.append(line)

        if current_note:
            notes.append("\n".join(current_note))

        return notes
