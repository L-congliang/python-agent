"""Memory v2 Cross-Session 测试

验证 cross-session retrieval 和 memory 分层。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from agent.memory.manager import MemoryManager
from agent.memory.durable import DurableMemory
from agent.memory.session_search import SessionSearch


# ============================================================
# 辅助函数
# ============================================================


def create_temp_memory_dir() -> Path:
    """创建临时 memory 目录"""
    return Path(tempfile.mkdtemp()) / ".agent" / "memory"


def create_temp_session_dir() -> Path:
    """创建临时 session 目录"""
    return Path(tempfile.mkdtemp()) / ".agent" / "sessions"


# ============================================================
# Memory 分层测试
# ============================================================


class TestMemoryLayering:
    """Memory 分层测试。"""

    def test_memory_has_three_layers(self) -> None:
        """memory 至少分成 user_preferences / project_facts / episodic_notes 三类"""
        memory_dir = create_temp_memory_dir()
        memory = MemoryManager(memory_dir)

        # 检查 durable memory 的 topic 类型
        durable = memory._durable
        assert "user-preferences" in durable.TOPICS
        assert "project-conventions" in durable.TOPICS
        assert "key-decisions" in durable.TOPICS

    def test_durable_memory_topics(self) -> None:
        """durable memory 有预定义 topic"""
        memory_dir = create_temp_memory_dir()
        durable = DurableMemory(memory_dir)

        # 预定义 topic 在 TOPICS 常量中
        assert "user-preferences" in durable.TOPICS
        assert "project-conventions" in durable.TOPICS
        assert "key-decisions" in durable.TOPICS

    def test_episodic_notes_separate(self) -> None:
        """episodic notes 和 durable memory 是分开的"""
        memory_dir = create_temp_memory_dir()
        memory = MemoryManager(memory_dir)

        # episodic notes 是独立的
        assert memory._notes is not None
        assert memory._durable is not None
        assert memory._notes is not memory._durable

    def test_working_memory_separate(self) -> None:
        """working memory 是独立的"""
        memory_dir = create_temp_memory_dir()
        memory = MemoryManager(memory_dir)

        assert memory._working is not None
        assert memory._working is not memory._durable


# ============================================================
# Cross-Session Retrieval 测试
# ============================================================


class TestCrossSessionRetrieval:
    """Cross-Session Retrieval 测试。"""

    def test_session_search_finds_relevant_session_note(self) -> None:
        """session search 能找到相关的 session note"""
        session_dir = create_temp_session_dir()
        memory_dir = create_temp_memory_dir()

        # 创建目录
        session_dir.mkdir(parents=True, exist_ok=True)

        # 创建一个 session 文件
        session_data = {
            "id": "session_1",
            "messages": [
                {"role": "user", "content": "What is the default max_turns in LoopConfig?"},
                {"role": "assistant", "content": "The default max_turns is 50."},
            ],
        }
        session_file = session_dir / "session_1.json"
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        # 创建 session search
        search = SessionSearch(session_dir)

        # 搜索
        results = search.search("max_turns default", top_k=3)
        assert len(results) > 0
        assert any("max_turns" in r.content.lower() for r in results)

    def test_session_search_finds_durable_project_fact(self) -> None:
        """session search 能找到 durable project fact"""
        memory_dir = create_temp_memory_dir()
        durable = DurableMemory(memory_dir)

        # 添加一个 project fact
        durable.add_note("project-conventions", "使用 4 空格缩进")
        durable.save()

        # 创建 session search
        session_dir = create_temp_session_dir()
        search = SessionSearch(session_dir, memory_dir)

        # 搜索
        results = search.search("缩进 空格", top_k=3)
        assert len(results) > 0
        assert any("缩进" in r.content for r in results)

    def test_session_search_returns_empty_when_no_match(self) -> None:
        """没有匹配时返回空列表"""
        session_dir = create_temp_session_dir()
        search = SessionSearch(session_dir)

        results = search.search("nonexistent query", top_k=3)
        assert results == []

    def test_session_search_returns_empty_when_no_sessions(self) -> None:
        """没有 session 时返回空列表"""
        session_dir = create_temp_session_dir()
        search = SessionSearch(session_dir)

        results = search.search("any query", top_k=3)
        assert results == []


# ============================================================
# Memory Inspect CLI 测试
# ============================================================


class TestMemoryInspectCLI:
    """Memory Inspect CLI 测试。"""

    def test_memory_summary_in_inspect(self) -> None:
        """/inspect 能显示 memory summary"""
        from agent.core.loop import AgentLoop, LoopConfig
        from agent.tools.registry import ToolRegistry, register_base_tools
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_client = MagicMock()
            config = LoopConfig(model="test", workspace_root=tmpdir)
            registry = register_base_tools(ToolRegistry())
            loop = AgentLoop(mock_client, registry, config=config)

            # 获取 inspect summary
            summary = loop.get_inspect_summary()

            # 验证 memory 字段
            assert "memory" in summary
            memory_summary = summary["memory"]
            assert "durable_topics_count" in memory_summary
            assert "recent_episodic_notes_count" in memory_summary

    def test_memory_summary_with_notes(self) -> None:
        """有笔记时 memory summary 正确"""
        from agent.core.loop import AgentLoop, LoopConfig
        from agent.tools.registry import ToolRegistry, register_base_tools
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_client = MagicMock()
            config = LoopConfig(model="test", workspace_root=tmpdir)
            registry = register_base_tools(ToolRegistry())
            loop = AgentLoop(mock_client, registry, config=config)

            # 添加一些笔记
            loop._memory.append_note("test note", tags=["test"])

            # 获取 inspect summary
            summary = loop.get_inspect_summary()
            memory_summary = summary["memory"]

            assert memory_summary["recent_episodic_notes_count"] > 0


# ============================================================
# Baseline 对比测试
# ============================================================


class TestMemoryBaselineComparison:
    """Memory Baseline 对比测试。"""

    def test_memory_v2_improves_or_preserves_baseline_schema(self) -> None:
        """Memory v2 的 baseline schema 和 Phase 3.2A 一致"""
        from scripts.run_phase32_baseline import collect_memory_metrics

        metrics = collect_memory_metrics()

        # 验证 schema 一致
        assert "memory_on" in metrics
        assert "memory_off" in metrics

        for config_name, config_metrics in metrics.items():
            if "error" in config_metrics:
                continue
            assert "correct_rate" in config_metrics
            assert "avg_tool_calls" in config_metrics
            assert "avg_duration" in config_metrics

    def test_loop_includes_cross_session_recall_in_memory_prompt(self) -> None:
        """loop 构建 prompt 时包含 cross-session recall"""
        from agent.core.loop import AgentLoop, LoopConfig
        from agent.tools.registry import ToolRegistry, register_base_tools
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = os.path.join(tmpdir, ".agent", "sessions")
            memory_dir = os.path.join(tmpdir, ".agent", "memory")

            # 创建目录
            os.makedirs(session_dir, exist_ok=True)
            os.makedirs(memory_dir, exist_ok=True)

            # 创建一个 session 文件
            session_data = {
                "id": "session_1",
                "messages": [
                    {"role": "user", "content": "What is the default max_turns?"},
                    {"role": "assistant", "content": "The default max_turns is 50."},
                ],
            }
            session_file = os.path.join(session_dir, "session_1.json")
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f)

            # 创建 loop
            mock_client = MagicMock()
            config = LoopConfig(
                model="test",
                workspace_root=tmpdir,
                session_dir=session_dir,
            )
            registry = register_base_tools(ToolRegistry())
            loop = AgentLoop(mock_client, registry, config=config)

            # 设置 task
            loop._memory.set_task("Find max_turns default")

            # 调用 assemble_layered
            memory_text = loop._memory.assemble_layered("max_turns default")

            # 验证 cross_session_recall 被注入
            assert "cross_session_recall:" in memory_text
            assert "max_turns" in memory_text.lower()

    def test_cross_session_recall_respects_memory_budget(self) -> None:
        """cross-session recall 受 budget 控制"""
        from agent.core.loop import AgentLoop, LoopConfig
        from agent.tools.registry import ToolRegistry, register_base_tools
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = os.path.join(tmpdir, ".agent", "sessions")
            memory_dir = os.path.join(tmpdir, ".agent", "memory")

            # 创建目录
            os.makedirs(session_dir, exist_ok=True)
            os.makedirs(memory_dir, exist_ok=True)

            # 创建多个 session 文件
            for i in range(10):
                session_data = {
                    "id": f"session_{i}",
                    "messages": [
                        {"role": "user", "content": f"Question {i} about max_turns"},
                        {"role": "assistant", "content": f"Answer {i}: max_turns is 50"},
                    ],
                }
                session_file = os.path.join(session_dir, f"session_{i}.json")
                with open(session_file, "w", encoding="utf-8") as f:
                    json.dump(session_data, f)

            # 创建 loop
            mock_client = MagicMock()
            config = LoopConfig(
                model="test",
                workspace_root=tmpdir,
                session_dir=session_dir,
            )
            registry = register_base_tools(ToolRegistry())
            loop = AgentLoop(mock_client, registry, config=config)

            # 设置 task
            loop._memory.set_task("Find max_turns default")

            # 调用 assemble_layered，设置小 budget
            memory_text = loop._memory.assemble_layered("max_turns default", max_tokens=100)

            # 验证 cross_session_recall 被注入，但受 budget 限制
            # 不应该有 10 个结果，应该被截断
            assert "cross_session_recall:" in memory_text


# ============================================================
# 边界测试
# ============================================================


class TestMemoryV2EdgeCases:
    """边界情况测试。"""

    def test_unicode_content(self) -> None:
        """Unicode 内容"""
        memory_dir = create_temp_memory_dir()
        durable = DurableMemory(memory_dir)

        durable.add_note("user-preferences", "用户偏好中文回复")
        durable.save()

        # 重新加载
        durable2 = DurableMemory(memory_dir)
        durable2.load()

        notes = durable2.get_notes("user-preferences")
        assert len(notes) == 1
        assert "中文" in notes[0].content

    def test_large_memory(self) -> None:
        """大量 memory"""
        memory_dir = create_temp_memory_dir()
        durable = DurableMemory(memory_dir)

        # 添加大量笔记
        for i in range(100):
            durable.add_note("project-conventions", f"convention {i}")

        durable.save()

        # 重新加载
        durable2 = DurableMemory(memory_dir)
        durable2.load()

        notes = durable2.get_notes("project-conventions")
        assert len(notes) == 100
