"""记忆渲染 - 给模型看的紧凑格式

设计决策:
- 为什么用"仪表盘"格式？
  模型需要快速获取关键信息
  结构化格式便于解析
  节省 token

- 为什么只显示有效的文件摘要？
  无效摘要会误导模型
  节省 token

- 为什么显示 episodic_notes 数量而不是全部？
  全部笔记会占用太多 token
  数量提示模型有笔记可用，需要时再检索
"""

from __future__ import annotations

from typing import Any

from agent.memory.working import WorkingMemory
from agent.memory.file_summaries import FileSummaries
from agent.memory.episodic import EpisodicNotes
from agent.memory.durable import DurableMemory


class MemoryRenderer:
    """记忆渲染器

    使用方式:
        renderer = MemoryRenderer(working, files, notes, durable)
        output = renderer.render()
    """

    def __init__(
        self,
        working: WorkingMemory,
        files: FileSummaries,
        notes: EpisodicNotes,
        durable: DurableMemory,
    ) -> None:
        """初始化

        Args:
            working: 工作记忆
            files: 文件摘要
            notes: 事件笔记
            durable: 持久记忆
        """
        self._working = working
        self._files = files
        self._notes = notes
        self._durable = durable

    def render(self) -> str:
        """渲染记忆为紧凑格式

        Returns:
            格式化的记忆字符串
        """
        parts = ["Memory:"]

        # 1. 任务摘要
        task = self._working.task_summary or "-"
        parts.append(f"  task: {task}")

        # 2. 最近文件
        recent_files = self._working.get_recent_files()
        if recent_files:
            files_str = ", ".join(recent_files[-5:])  # 最多显示 5 个
            parts.append(f"  recent_files: {files_str}")
        else:
            parts.append("  recent_files: -")

        # 3. 文件摘要（仅有效的）
        valid_summaries = []
        for path, summary in self._files.get_all().items():
            if self._files.is_fresh(path):
                valid_summaries.append(f"{path}: {summary.content[:50]}...")

        if valid_summaries:
            parts.append("  file_summaries:")
            for s in valid_summaries[:3]:  # 最多显示 3 个
                parts.append(f"    - {s}")
        else:
            parts.append("  file_summaries: -")

        # 4. 事件笔记数量
        notes_count = len(self._notes)
        parts.append(f"  episodic_notes: {notes_count} notes")

        # 5. 持久记忆主题
        durable_topics = self._durable.get_all_topics()
        if durable_topics:
            parts.append(f"  durable_topics: {', '.join(durable_topics)}")
        else:
            parts.append("  durable_topics: -")

        return "\n".join(parts)

    def render_task(self) -> str:
        """渲染 task 部分

        Returns:
            task 文本，无 task 时返回空字符串
        """
        task = self._working.task_summary
        if not task:
            return ""
        return f"task: {task}"

    def render_recent_files(self, max_files: int = 5) -> str:
        """渲染 recent_files 部分

        Args:
            max_files: 最大文件数

        Returns:
            recent_files 文本
        """
        recent = self._working.get_recent_files()
        if not recent:
            return "recent_files: -"
        files_str = ", ".join(recent[-max_files:])
        return f"recent_files: {files_str}"

    def render_file_summaries(self, summaries: list[dict[str, Any]]) -> str:
        """渲染 file_summaries 部分（结构化版本）

        Args:
            summaries: select_relevant_file_summaries 返回的列表

        Returns:
            file_summaries 文本
        """
        if not summaries:
            return "file_summaries: -"
        parts = ["file_summaries:"]
        for s in summaries:
            path = s.get("path", "")
            responsibility = s.get("responsibility", "")
            key_entities = s.get("key_entities", [])
            recent_focus = s.get("recent_focus", "")

            # 构建结构化摘要
            summary_parts = [f"  - {path}:"]
            if responsibility:
                summary_parts.append(f"      职责: {responsibility}")
            if key_entities:
                entities_str = ", ".join(key_entities[:5])  # 最多显示 5 个
                summary_parts.append(f"      关键实体: {entities_str}")
            if recent_focus:
                summary_parts.append(f"      最近重点: {recent_focus}")

            parts.append("\n".join(summary_parts))
        return "\n".join(parts)

    def render_episodic_notes(self, notes: list[dict[str, Any]]) -> str:
        """渲染 episodic_notes 部分

        Args:
            notes: search_notes 返回的列表

        Returns:
            episodic_notes 文本
        """
        if not notes:
            return ""
        parts = ["episodic_notes:"]
        for n in notes:
            tags = ", ".join(n.get("tags", []))
            tag_str = f" [{tags}]" if tags else ""
            parts.append(f"  - {n['text']}{tag_str}")
        return "\n".join(parts)

    def render_compact(self) -> str:
        """渲染为更紧凑的格式（用于 token 受限场景）

        Returns:
            更紧凑的记忆字符串
        """
        parts = []

        # 只包含最关键的信息
        task = self._working.task_summary
        if task:
            parts.append(f"Task: {task}")

        recent = self._working.get_recent_files()
        if recent:
            parts.append(f"Files: {', '.join(recent[-3:])}")

        if self._notes:
            parts.append(f"Notes: {len(self._notes)}")

        return " | ".join(parts) if parts else "Memory: empty"
