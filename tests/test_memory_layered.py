"""MemoryManager 分层组装测试"""

from __future__ import annotations

import time
from pathlib import Path

from agent.memory.manager import MemoryManager
from agent.memory.renderer import MemoryRenderer
from agent.memory.working import WorkingMemory
from agent.memory.file_summaries import FileSummaries
from agent.memory.episodic import EpisodicNotes
from agent.memory.durable import DurableMemory


def _make_summary(mm: MemoryManager, tmp_path: Path, name: str, content: str) -> str:
    """创建真实文件并更新摘要"""
    f = tmp_path / name
    f.write_text(content)
    stat = f.stat()
    mm.update_file_summary(str(f), content, stat.st_mtime, stat.st_size)
    return str(f)


class TestSelectRelevantFileSummaries:
    """select_relevant_file_summaries() 测试"""

    def test_recent_files_priority(self, tmp_path: Path) -> None:
        """recent_files 中的文件优先"""
        mm = MemoryManager()
        mm.set_task("test task")
        path_a = _make_summary(mm, tmp_path, "a.py", "content a")
        path_b = _make_summary(mm, tmp_path, "b.py", "content b")
        path_c = _make_summary(mm, tmp_path, "c.py", "content c")
        mm.touch_file(path_a)
        mm.touch_file(path_b)
        # 不 touch path_c

        result = mm.select_relevant_file_summaries("test", top_k=2)
        paths = [r["path"] for r in result]
        assert path_a in paths
        assert path_b in paths

    def test_keyword_match(self, tmp_path: Path) -> None:
        """路径名与 query 关键词重叠的文件被选中"""
        mm = MemoryManager()
        path_auth = _make_summary(mm, tmp_path, "login.py", "auth content")
        path_api = _make_summary(mm, tmp_path, "client.py", "api content")

        result = mm.select_relevant_file_summaries("login", top_k=2)
        paths = [r["path"] for r in result]
        assert path_auth in paths

    def test_only_fresh_summaries(self, tmp_path: Path) -> None:
        """只返回 fresh 的 summaries"""
        mm = MemoryManager()
        path_new = _make_summary(mm, tmp_path, "new.py", "new content")
        # 手动添加一个过期摘要
        mm._files._summaries["/fake/old.py"] = type("S", (), {
            "content": "old", "freshness": "0:0", "mtime": 0, "size": 0
        })()

        result = mm.select_relevant_file_summaries("test", top_k=5)
        paths = [r["path"] for r in result]
        assert path_new in paths
        assert "/fake/old.py" not in paths

    def test_empty_when_no_summaries(self) -> None:
        """没有 summaries 时返回空列表"""
        mm = MemoryManager()
        result = mm.select_relevant_file_summaries("test", top_k=3)
        assert result == []


class TestAssembleLayered:
    """assemble_layered() 测试"""

    def test_contains_task(self) -> None:
        """包含 task"""
        mm = MemoryManager()
        mm.set_task("fix the bug")
        result = mm.assemble_layered("test query")
        assert "fix the bug" in result

    def test_contains_recent_files(self, tmp_path: Path) -> None:
        """包含 recent_files"""
        mm = MemoryManager()
        mm.set_task("test")
        f = tmp_path / "a.py"
        f.write_text("x")
        mm.touch_file(str(f))
        result = mm.assemble_layered("test query")
        assert str(f) in result

    def test_contains_file_summaries(self, tmp_path: Path) -> None:
        """包含 file_summaries"""
        mm = MemoryManager()
        mm.set_task("test")
        path = _make_summary(mm, tmp_path, "a.py", "def hello(): pass")
        result = mm.assemble_layered("test query")
        assert "a.py" in result

    def test_contains_episodic_notes(self) -> None:
        """包含 episodic_notes（当 search 有命中时）"""
        mm = MemoryManager()
        mm.set_task("test")
        mm.append_note("API_KEY is sk-xxx", tags=["config"])
        result = mm.assemble_layered("API_KEY")
        assert "API_KEY" in result or "sk-xxx" in result

    def test_no_notes_when_empty(self) -> None:
        """没有 notes 时不注入 episodic_notes section"""
        mm = MemoryManager()
        mm.set_task("test")
        result = mm.assemble_layered("test query")
        # 不应该有 episodic_notes section
        assert "episodic_notes:" not in result

    def test_respects_max_tokens(self) -> None:
        """超出 max_tokens 时截断"""
        mm = MemoryManager()
        mm.set_task("test " + "x" * 5000)
        result = mm.assemble_layered("test query", max_tokens=50)
        # 应该被截断
        assert len(result) < 5000

    def test_assembly_order(self) -> None:
        """组装顺序：task 在前，recent_files 在后"""
        mm = MemoryManager()
        mm.set_task("my task")
        f = Path("/tmp/test_a.py")
        mm._working.touch_file("src/a.py")
        result = mm.assemble_layered("test query")
        task_pos = result.find("my task")
        files_pos = result.find("recent_files:")
        assert task_pos < files_pos


class TestRendererLayered:
    """Renderer 分层渲染方法测试"""

    def test_render_task(self) -> None:
        """render_task() 返回 task 内容"""
        working = WorkingMemory()
        working.set_task_summary("fix bug")
        renderer = MemoryRenderer(working, FileSummaries(), EpisodicNotes(), DurableMemory())
        result = renderer.render_task()
        assert "fix bug" in result

    def test_render_task_empty(self) -> None:
        """render_task() 无 task 时返回空"""
        working = WorkingMemory()
        renderer = MemoryRenderer(working, FileSummaries(), EpisodicNotes(), DurableMemory())
        result = renderer.render_task()
        assert result == ""

    def test_render_recent_files(self) -> None:
        """render_recent_files() 返回文件列表"""
        working = WorkingMemory()
        working.touch_file("a.py")
        working.touch_file("b.py")
        renderer = MemoryRenderer(working, FileSummaries(), EpisodicNotes(), DurableMemory())
        result = renderer.render_recent_files()
        assert "a.py" in result
        assert "b.py" in result

    def test_render_file_summaries(self) -> None:
        """render_file_summaries() 返回摘要列表"""
        renderer = MemoryRenderer(WorkingMemory(), FileSummaries(), EpisodicNotes(), DurableMemory())
        summaries = [{"path": "a.py", "content": "def hello(): pass"}]
        result = renderer.render_file_summaries(summaries)
        assert "a.py" in result
        assert "hello" in result

    def test_render_episodic_notes(self) -> None:
        """render_episodic_notes() 返回笔记内容"""
        renderer = MemoryRenderer(WorkingMemory(), FileSummaries(), EpisodicNotes(), DurableMemory())
        notes = [{"text": "API_KEY is sk-xxx", "tags": ["config"], "score": 0.9, "match_type": "keyword"}]
        result = renderer.render_episodic_notes(notes)
        assert "API_KEY" in result
        assert "sk-xxx" in result

    def test_render_episodic_notes_empty(self) -> None:
        """render_episodic_notes() 空列表返回空字符串"""
        renderer = MemoryRenderer(WorkingMemory(), FileSummaries(), EpisodicNotes(), DurableMemory())
        result = renderer.render_episodic_notes([])
        assert result == ""
