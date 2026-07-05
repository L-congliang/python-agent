"""记忆检索 - 基于结构标签和关键词的检索

设计决策:
- 为什么先看结构标签匹配？
  结构标签（kind, entity, file_path）是精确信息，精确度高
  快速过滤，减少后续计算量

- 为什么再看关键词重叠？
  结构标签可能不够精确，关键词提供更细粒度匹配
  用简单的字符串包含，不需要复杂的 NLP

- 为什么最后看新近度？
  新近度作为 tiebreaker
  最近的笔记更可能相关

- 为什么返回最相关的 3 条？
  太少会丢失信息，太多会占用 token
  3 条是经验值，覆盖典型查询需求
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.memory.episodic import EpisodicNotes, Note


@dataclass
class RetrievalResult:
    """检索结果

    Attributes:
        note: 匹配的笔记
        score: 相关性分数（0-1）
        match_type: 匹配类型（structure, tag, keyword, recent）
    """
    note: Note
    score: float
    match_type: str


class Retrieval:
    """记忆检索器

    使用方式:
        retrieval = Retrieval(notes)
        results = retrieval.search("main.py 修复", top_k=3)
    """

    def __init__(self, notes: EpisodicNotes) -> None:
        """初始化

        Args:
            notes: 事件笔记管理器
        """
        self._notes = notes

    def search(
        self,
        query: str,
        top_k: int = 3,
        tags: list[str] | None = None,
    ) -> list[RetrievalResult]:
        """搜索相关笔记

        Args:
            query: 查询文本
            tags: 标签过滤

        Returns:
            最相关的笔记列表
        """
        all_notes = self._notes.get_all()
        if not all_notes:
            return []

        # 计算每个笔记的分数
        scored_notes: list[RetrievalResult] = []

        for note in all_notes:
            score, match_type = self._score_note(note, query, tags)
            if score > 0:
                scored_notes.append(RetrievalResult(
                    note=note,
                    score=score,
                    match_type=match_type,
                ))

        # 按分数排序（降序）
        scored_notes.sort(key=lambda x: x.score, reverse=True)

        # 返回 top_k
        return scored_notes[:top_k]

    def _score_note(
        self,
        note: Note,
        query: str,
        tags: list[str] | None,
    ) -> tuple[float, str]:
        """计算笔记的相关性分数（结构匹配优先）

        Args:
            note: 笔记
            query: 查询文本
            tags: 标签过滤

        Returns:
            (分数, 匹配类型)
        """
        score = 0.0
        match_type = ""

        # 1. 结构标签匹配（最高权重）
        structure_score = self._score_structure_match(note, query)
        if structure_score > score:
            score = structure_score
            match_type = "structure"

        # 2. 标签精确匹配
        if tags:
            tag_matches = sum(1 for t in tags if t in note.tags)
            if tag_matches > 0:
                tag_score = 0.8 + (tag_matches * 0.1)
                if tag_score > score:
                    score = tag_score
                    match_type = "tag"

        # 3. 关键词匹配
        if score < 0.8:
            query_lower = query.lower()
            note_lower = note.text.lower()

            # 简单的关键词重叠
            query_words = set(query_lower.split())
            note_words = set(note_lower.split())
            overlap = query_words & note_words

            if overlap:
                keyword_score = len(overlap) / len(query_words) * 0.6
                if keyword_score > score:
                    score = keyword_score
                    match_type = "keyword"

        # 4. 新近度（作为 tiebreaker）
        if score < 0.3:
            # 简单的索引位置作为新近度
            all_notes = self._notes.get_all()
            if note in all_notes:
                recency = all_notes.index(note) / len(all_notes)
                recency_score = recency * 0.3
                if recency_score > score:
                    score = recency_score
                    match_type = "recent"

        return score, match_type

    def _score_structure_match(self, note: Note, query: str) -> float:
        """计算结构标签匹配分数

        Args:
            note: 笔记
            query: 查询文本

        Returns:
            结构匹配分数（0-1）
        """
        score = 0.0
        query_lower = query.lower()
        query_words = set(query_lower.split())

        # 1. file_path 匹配（高权重）
        if note.file_path:
            file_path_lower = note.file_path.lower()
            # 检查查询中是否包含文件名
            file_name = file_path_lower.split("/")[-1].split("\\")[-1]
            if file_name and file_name in query_lower:
                score += 0.4
            # 检查路径关键词重叠
            path_words = set(file_path_lower.replace("/", " ").replace("\\", " ").replace(".", " ").split())
            path_overlap = path_words & query_words
            if path_overlap:
                score += 0.2 * len(path_overlap)

        # 2. entity 匹配（高权重）
        if note.entity:
            entity_lower = note.entity.lower()
            # 检查查询中是否包含实体名
            if entity_lower in query_lower:
                score += 0.5
            # 检查实体关键词重叠
            entity_words = set(entity_lower.split("_"))
            entity_overlap = entity_words & query_words
            if entity_overlap:
                score += 0.3 * len(entity_overlap)

        # 3. kind 匹配（中权重）
        if note.kind:
            kind_lower = note.kind.lower()
            # 检查查询中是否包含类型关键词
            kind_keywords = {
                "fact": ["what", "value", "number", "string", "exact"],
                "constraint": ["must", "should", "not", "only", "constraint"],
                "conflict": ["conflict", "different", "wrong", "error"],
                "observation": ["notice", "see", "found", "observe"],
                "decision": ["decide", "choose", "will", "plan"],
            }
            if kind_lower in kind_keywords:
                for keyword in kind_keywords[kind_lower]:
                    if keyword in query_lower:
                        score += 0.2
                        break

        # 4. importance 匹配（低权重）
        if note.importance == "high":
            score += 0.1

        return min(score, 1.0)
