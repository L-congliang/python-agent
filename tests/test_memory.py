"""记忆系统测试

测试覆盖：
- WorkingMemory：任务摘要、LRU 文件访问
- FileSummaries：摘要生成、freshness 校验
- EpisodicNotes：笔记添加、去重、容量限制
- Retrieval：标签匹配、关键词匹配
- DurableMemory：持久记忆加载、保存
- MemoryManager：统一接口
"""

import os
import tempfile
from pathlib import Path

import pytest

from agent.memory.working import WorkingMemory
from agent.memory.file_summaries import FileSummaries
from agent.memory.episodic import EpisodicNotes
from agent.memory.retrieval import Retrieval
from agent.memory.durable import DurableMemory
from agent.memory.manager import MemoryManager


# ========== WorkingMemory 测试 ==========


class TestWorkingMemory:
    """WorkingMemory 测试"""

    def test_set_task_summary(self):
        """测试设置任务摘要"""
        memory = WorkingMemory()
        memory.set_task_summary("修复 bug")
        assert memory.task_summary == "修复 bug"

    def test_touch_file_lru(self):
        """测试文件访问 LRU"""
        memory = WorkingMemory()

        # 依次访问文件
        memory.touch_file("file_a")
        memory.touch_file("file_b")
        memory.touch_file("file_a")  # file_a 移到最近

        files = memory.get_recent_files()
        assert files == ["file_b", "file_a"]

    def test_touch_file_lru_limit(self):
        """测试 LRU 淘汰"""
        memory = WorkingMemory()

        # 添加 9 个文件（超过 MAX_RECENT_FILES=8）
        for i in range(9):
            memory.touch_file(f"file_{i}")

        files = memory.get_recent_files()
        assert len(files) == 8
        assert "file_0" not in files  # 最早的被淘汰
        assert "file_8" in files  # 最新的保留

    def test_clear(self):
        """测试清空"""
        memory = WorkingMemory()
        memory.set_task_summary("任务")
        memory.touch_file("file")
        memory.clear()

        assert memory.task_summary == ""
        assert memory.get_recent_files() == []

    def test_is_empty(self):
        """测试是否为空"""
        memory = WorkingMemory()
        assert memory.is_empty() is True

        memory.set_task_summary("任务")
        assert memory.is_empty() is False


# ========== FileSummaries 测试 ==========


class TestFileSummaries:
    """FileSummaries 测试"""

    def test_update_summary(self):
        """测试更新摘要"""
        summaries = FileSummaries()
        content = "x" * 200  # 超过 180 字符

        summary = summaries.update("test.py", content, file_mtime=123, file_size=200)

        assert summary.path == "test.py"
        assert len(summary.content) == 180 + 3  # 180 + "..."
        assert summary.total_chars == 200

    def test_get_summary(self):
        """测试获取摘要"""
        summaries = FileSummaries()
        summaries.update("test.py", "content", file_mtime=123, file_size=7)

        summary = summaries.get("test.py")
        assert summary is not None
        assert summary.path == "test.py"

    def test_is_fresh(self):
        """测试 freshness 校验"""
        summaries = FileSummaries()

        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("content")
            temp_path = f.name

        try:
            # 更新摘要
            stat = os.stat(temp_path)
            summaries.update(temp_path, "content", stat.st_mtime, stat.st_size)

            # freshness 应该通过
            assert summaries.is_fresh(temp_path) is True

            # 修改文件后 freshness 失败
            with open(temp_path, "w") as f:
                f.write("modified content")

            assert summaries.is_fresh(temp_path) is False
        finally:
            os.unlink(temp_path)

    def test_invalidate(self):
        """测试使摘要失效"""
        summaries = FileSummaries()
        summaries.update("test.py", "content", file_mtime=123, file_size=7)

        summaries.invalidate("test.py")
        assert summaries.get("test.py") is None

    def test_evict_oldest(self):
        """测试淘汰最旧的摘要"""
        summaries = FileSummaries(max_summaries=2)

        summaries.update("a.py", "a", file_mtime=1, file_size=1)
        summaries.update("b.py", "b", file_mtime=2, file_size=1)
        summaries.update("c.py", "c", file_mtime=3, file_size=1)

        assert summaries.get("a.py") is None  # 被淘汰
        assert summaries.get("c.py") is not None


# ========== EpisodicNotes 测试 ==========


class TestEpisodicNotes:
    """EpisodicNotes 测试"""

    def test_append_note(self):
        """测试添加笔记"""
        notes = EpisodicNotes()
        note = notes.append("发现 bug", tags=["bug"])

        assert note is not None
        assert note.text == "发现 bug"
        assert note.tags == ["bug"]
        assert len(notes) == 1

    def test_append_duplicate(self):
        """测试去重"""
        notes = EpisodicNotes()
        notes.append("发现 bug")
        note = notes.append("发现 bug")  # 重复

        assert note is None
        assert len(notes) == 1

    def test_max_notes_limit(self):
        """测试容量限制"""
        notes = EpisodicNotes(max_notes=2)

        notes.append("笔记 1")
        notes.append("笔记 2")
        notes.append("笔记 3")  # 触发淘汰

        assert len(notes) == 2
        all_notes = notes.get_all()
        assert all_notes[0].text == "笔记 2"
        assert all_notes[1].text == "笔记 3"

    def test_get_recent(self):
        """测试获取最近的笔记"""
        notes = EpisodicNotes()
        notes.append("笔记 1")
        notes.append("笔记 2")
        notes.append("笔记 3")

        recent = notes.get_recent(2)
        assert len(recent) == 2
        assert recent[0].text == "笔记 2"
        assert recent[1].text == "笔记 3"

    def test_get_by_tag(self):
        """测试按标签获取"""
        notes = EpisodicNotes()
        notes.append("bug 1", tags=["bug"])
        notes.append("feature 1", tags=["feature"])
        notes.append("bug 2", tags=["bug"])

        bugs = notes.get_by_tag("bug")
        assert len(bugs) == 2

    def test_note_max_length(self):
        """测试笔记最大长度"""
        notes = EpisodicNotes()
        long_text = "x" * 600  # 超过 500 字符

        note = notes.append(long_text)
        assert len(note.text) == 500 + 3  # 500 + "..."


# ========== Retrieval 测试 ==========


class TestRetrieval:
    """Retrieval 测试"""

    def test_search_by_tag(self):
        """测试标签匹配"""
        notes = EpisodicNotes()
        notes.append("bug 在 main.py", tags=["bug"])
        notes.append("feature request", tags=["feature"])

        retrieval = Retrieval(notes)
        results = retrieval.search("bug", tags=["bug"])

        # 标签匹配的应该排在最前面
        assert len(results) > 0
        assert results[0].match_type == "tag"
        assert "bug" in results[0].note.tags

    def test_search_by_keyword(self):
        """测试关键词匹配"""
        notes = EpisodicNotes()
        notes.append("main.py 有 bug")
        notes.append("test.py 通过")

        retrieval = Retrieval(notes)
        results = retrieval.search("main.py bug")

        assert len(results) > 0
        assert results[0].match_type == "keyword"

    def test_search_no_match(self):
        """测试无匹配"""
        notes = EpisodicNotes()
        notes.append("无关内容")

        retrieval = Retrieval(notes)
        results = retrieval.search("完全不相关")

        assert len(results) == 0

    def test_search_top_k(self):
        """测试返回数量"""
        notes = EpisodicNotes()
        for i in range(10):
            notes.append(f"笔记 {i}")

        retrieval = Retrieval(notes)
        results = retrieval.search("笔记", top_k=3)

        assert len(results) == 3


# ========== DurableMemory 测试 ==========


class TestDurableMemory:
    """DurableMemory 测试"""

    def test_add_note(self):
        """测试添加持久笔记"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = DurableMemory(tmpdir)
            memory.add_note("project-conventions", "使用 4 空格缩进")

            notes = memory.get_notes("project-conventions")
            assert len(notes) == 1
            assert notes[0].content == "使用 4 空格缩进"

    def test_save_and_load(self):
        """测试保存和加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 添加笔记
            memory1 = DurableMemory(tmpdir)
            memory1.add_note("project-conventions", "使用 4 空格缩进")
            memory1.save()

            # 重新加载
            memory2 = DurableMemory(tmpdir)
            memory2.load()

            notes = memory2.get_notes("project-conventions")
            assert len(notes) == 1
            assert notes[0].content == "使用 4 空格缩进"

    def test_get_all_topics(self):
        """测试获取所有主题"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = DurableMemory(tmpdir)
            memory.add_note("project-conventions", "规则 1")
            memory.add_note("user-preferences", "偏好 1")

            topics = memory.get_all_topics()
            assert "project-conventions" in topics
            assert "user-preferences" in topics


# ========== MemoryManager 测试 ==========


class TestMemoryManager:
    """MemoryManager 测试"""

    def test_set_task(self):
        """测试设置任务"""
        manager = MemoryManager()
        manager.set_task("修复 bug")

        assert manager.get_task() == "修复 bug"

    def test_touch_file(self):
        """测试记录文件访问"""
        manager = MemoryManager()
        manager.touch_file("src/main.py")

        files = manager.get_recent_files()
        assert "src/main.py" in files

    def test_append_note(self):
        """测试添加笔记"""
        manager = MemoryManager()
        result = manager.append_note("发现 bug", tags=["bug"])

        assert result is True

    def test_search_notes(self):
        """测试搜索笔记"""
        manager = MemoryManager()
        manager.append_note("main.py 有 bug", tags=["bug"])

        results = manager.search_notes("bug", tags=["bug"])
        assert len(results) > 0

    def test_render(self):
        """测试渲染"""
        manager = MemoryManager()
        manager.set_task("修复 bug")
        manager.touch_file("src/main.py")

        output = manager.render()
        assert "Memory:" in output
        assert "修复 bug" in output
        assert "src/main.py" in output

    def test_clear_session(self):
        """测试清空会话记忆"""
        manager = MemoryManager()
        manager.set_task("任务")
        manager.touch_file("file")
        manager.append_note("笔记")

        manager.clear_session()

        assert manager.get_task() == ""
        assert manager.get_recent_files() == []
