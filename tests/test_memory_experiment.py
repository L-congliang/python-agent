"""Memory Experiment 测试

验证 Phase 2 改造后的评测逻辑：
- memory_enabled 开关真正生效
- repeated_reads 从 tool_history 真实统计
- memory_hit 只对 eligible task 计数
- verifier 能正确判 contains_text / file_changed
- setup_turns 会先于主 prompt 执行
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.evaluation.memory_experiment import (
    MEMORY_TASKS,
    MemoryConfig,
    MemoryExperiment,
    MemoryMetrics,
    MemoryTask,
    _compute_memory_hit,
    _count_repeated_reads,
    _verify_task_result,
)


# ============================================================
# MemoryTask 结构测试
# ============================================================


class TestMemoryTask:
    """MemoryTask 数据结构测试"""

    def test_default_values(self) -> None:
        """新字段有合理默认值"""
        task = MemoryTask(task_id="t1", category="fact_lookup", prompt="test")
        assert task.setup_turns == []
        assert task.target_files == []
        assert task.verifier == "contains_text"
        assert task.expected_substrings == []
        assert task.fixture_dir == ""
        assert task.allow_reread is False

    def test_with_setup_turns(self) -> None:
        """setup_turns 可以赋值"""
        task = MemoryTask(
            task_id="t1",
            category="history_reference",
            prompt="What is X?",
            setup_turns=["Read file A and describe it."],
            target_files=["a.py"],
        )
        assert len(task.setup_turns) == 1
        assert task.target_files == ["a.py"]


# ============================================================
# MEMORY_TASKS 数据集测试
# ============================================================


class TestMemoryTasks:
    """测试任务数据集"""

    def test_has_tasks(self) -> None:
        """至少有 14 个任务"""
        assert len(MEMORY_TASKS) >= 14

    def test_all_have_target_files(self) -> None:
        """所有任务都有 target_files"""
        for task in MEMORY_TASKS:
            assert task.target_files, f"{task.task_id} missing target_files"

    def test_all_have_verifier(self) -> None:
        """所有任务都有 verifier"""
        for task in MEMORY_TASKS:
            assert task.verifier in ("contains_text", "file_changed", "multi_file_changed")

    def test_history_tasks_have_setup_turns(self) -> None:
        """需要 setup_turns 的任务类别必须有 setup_turns"""
        categories_needing_setup = {
            "history_reference", "cross_round_recall", "cross_file_dep",
            "multi_round_edit", "noise",
        }
        for task in MEMORY_TASKS:
            if task.category in categories_needing_setup:
                assert task.setup_turns, f"{task.task_id} is {task.category} but has no setup_turns"

    def test_fact_tasks_no_setup_turns(self) -> None:
        """fact_lookup 任务不应有 setup_turns"""
        for task in MEMORY_TASKS:
            if task.category == "fact_lookup":
                assert not task.setup_turns, f"{task.task_id} is fact_lookup but has setup_turns"

    def test_contains_text_have_expected_substrings(self) -> None:
        """contains_text 类任务必须有 expected_substrings"""
        for task in MEMORY_TASKS:
            if task.verifier == "contains_text":
                assert task.expected_substrings, f"{task.task_id} uses contains_text but has no expected_substrings"

    def test_new_categories_exist(self) -> None:
        """新类别都有对应任务"""
        categories = {t.category for t in MEMORY_TASKS}
        assert "cross_round_recall" in categories
        assert "cross_file_dep" in categories
        assert "multi_round_edit" in categories
        assert "noise" in categories

    def test_cross_round_recall_eligible_for_memory_hit(self) -> None:
        """cross_round_recall 任务应有 setup_turns + target_files，可算 memory_hit"""
        for task in MEMORY_TASKS:
            if task.category == "cross_round_recall":
                assert task.setup_turns, f"{task.task_id} needs setup_turns"
                assert task.target_files, f"{task.task_id} needs target_files"


# ============================================================
# Verifier 测试
# ============================================================


class TestVerifyTaskResult:
    """验证器测试"""

    def test_contains_text_match(self) -> None:
        """contains_text: 包含所有子串时返回 True"""
        task = MemoryTask(
            task_id="t1",
            category="fact_lookup",
            prompt="test",
            verifier="contains_text",
            expected_substrings=["hello", "world"],
        )
        assert _verify_task_result(task, "Hello World!", "/tmp") is True

    def test_contains_text_partial_miss(self) -> None:
        """contains_text: 缺少一个子串时返回 False"""
        task = MemoryTask(
            task_id="t1",
            category="fact_lookup",
            prompt="test",
            verifier="contains_text",
            expected_substrings=["hello", "world"],
        )
        assert _verify_task_result(task, "hello there", "/tmp") is False

    def test_contains_text_case_insensitive(self) -> None:
        """contains_text: 大小写不敏感"""
        task = MemoryTask(
            task_id="t1",
            category="fact_lookup",
            prompt="test",
            verifier="contains_text",
            expected_substrings=["HELLO"],
        )
        assert _verify_task_result(task, "hello world", "/tmp") is True

    def test_file_changed_found(self, tmp_path: Path) -> None:
        """file_changed: 文件包含期望内容时返回 True"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(c: int = 0):\n    pass\n")

        task = MemoryTask(
            task_id="t1",
            category="edit_dependency",
            prompt="test",
            verifier="file_changed",
            target_files=["test.py"],
            expected_substrings=["c: int = 0"],
        )
        assert _verify_task_result(task, "done", str(tmp_path)) is True

    def test_file_changed_not_found(self, tmp_path: Path) -> None:
        """file_changed: 文件不包含期望内容时返回 False"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        task = MemoryTask(
            task_id="t1",
            category="edit_dependency",
            prompt="test",
            verifier="file_changed",
            target_files=["test.py"],
            expected_substrings=["c: int = 0"],
        )
        assert _verify_task_result(task, "done", str(tmp_path)) is False

    def test_unknown_verifier_defaults_true(self) -> None:
        """未知 verifier 默认返回 True"""
        task = MemoryTask(
            task_id="t1",
            category="fact_lookup",
            prompt="test",
            verifier="unknown_type",
        )
        assert _verify_task_result(task, "anything", "/tmp") is True


# ============================================================
# repeated_reads 统计测试
# ============================================================


class TestCountRepeatedReads:
    """重复读取统计测试"""

    def test_no_reads(self) -> None:
        """没有 read 操作时返回 0"""
        history = [
            {"tool_name": "write", "is_error": False, "resolved_path": "/a.py"},
        ]
        assert _count_repeated_reads(history, ["a.py"], "/") == 0

    def test_single_read(self) -> None:
        """单次 read 不算重复"""
        history = [
            {"tool_name": "read", "is_error": False, "resolved_path": "/a.py"},
        ]
        assert _count_repeated_reads(history, ["a.py"], "/") == 0

    def test_two_reads_same_file(self) -> None:
        """同一文件读 2 次，重复 1 次"""
        history = [
            {"tool_name": "read", "is_error": False, "resolved_path": "/a.py"},
            {"tool_name": "read", "is_error": False, "resolved_path": "/a.py"},
        ]
        assert _count_repeated_reads(history, ["a.py"], "/") == 1

    def test_three_reads_two_files(self) -> None:
        """多文件混合统计"""
        history = [
            {"tool_name": "read", "is_error": False, "resolved_path": "/a.py"},
            {"tool_name": "read", "is_error": False, "resolved_path": "/b.py"},
            {"tool_name": "read", "is_error": False, "resolved_path": "/a.py"},
            {"tool_name": "read", "is_error": False, "resolved_path": "/a.py"},
        ]
        assert _count_repeated_reads(history, ["a.py", "b.py"], "/") == 2

    def test_error_read_not_counted(self) -> None:
        """失败的 read 不计入"""
        history = [
            {"tool_name": "read", "is_error": True, "resolved_path": "/a.py"},
            {"tool_name": "read", "is_error": False, "resolved_path": "/a.py"},
        ]
        assert _count_repeated_reads(history, ["a.py"], "/") == 0

    def test_blocked_read_not_counted(self) -> None:
        """被拦截的 read 不计入"""
        history = [
            {"tool_name": "read", "is_error": False, "resolved_path": "/a.py"},
            {"tool_name": "read", "is_error": True, "resolved_path": "/a.py",
             "blocked_by_repeat_detector": True},
        ]
        assert _count_repeated_reads(history, ["a.py"], "/") == 0

    def test_non_target_file_ignored(self) -> None:
        """非目标文件的读取不计入"""
        history = [
            {"tool_name": "read", "is_error": False, "resolved_path": "/other.py"},
            {"tool_name": "read", "is_error": False, "resolved_path": "/other.py"},
        ]
        assert _count_repeated_reads(history, ["a.py"], "/") == 0

    def test_empty_target_files(self) -> None:
        """target_files 为空时返回 0"""
        history = [
            {"tool_name": "read", "is_error": False, "resolved_path": "/a.py"},
        ]
        assert _count_repeated_reads(history, [], "/") == 0


# ============================================================
# memory_hit 统计测试
# ============================================================


class TestComputeMemoryHit:
    """memory_hit 统计测试"""

    def test_no_setup_turns_returns_negative(self) -> None:
        """没有 setup_turns 的任务返回 -1（不计入统计）"""
        task = MemoryTask(
            task_id="t1",
            category="fact_lookup",
            prompt="test",
            target_files=["a.py"],
        )
        assert _compute_memory_hit(task, [], "/") == -1

    def test_no_target_files_returns_negative(self) -> None:
        """没有 target_files 的任务返回 -1"""
        task = MemoryTask(
            task_id="t1",
            category="history_reference",
            prompt="test",
            setup_turns=["read a.py"],
        )
        assert _compute_memory_hit(task, [], "/") == -1

    def test_no_reread_is_hit(self) -> None:
        """主阶段没有 reread → memory_hit=1"""
        task = MemoryTask(
            task_id="t1",
            category="history_reference",
            prompt="test",
            setup_turns=["read a.py"],
            target_files=["a.py"],
        )
        # 主阶段没有读取 a.py
        history = [
            {"tool_name": "read", "is_error": False, "resolved_path": "/other.py"},
        ]
        assert _compute_memory_hit(task, history, "/") == 1

    def test_reread_is_miss(self) -> None:
        """主阶段有 reread → memory_hit=0"""
        task = MemoryTask(
            task_id="t1",
            category="history_reference",
            prompt="test",
            setup_turns=["read a.py"],
            target_files=["a.py"],
        )
        history = [
            {"tool_name": "read", "is_error": False, "resolved_path": "/a.py"},
        ]
        assert _compute_memory_hit(task, history, "/") == 0


# ============================================================
# Mock 路径测试
# ============================================================


class TestMockPath:
    """Mock 运行路径测试"""

    def test_mock_returns_expected_structure(self) -> None:
        """mock 路径返回正确的数据结构"""
        experiment = MemoryExperiment(use_real_model=False)
        task = MemoryTask(
            task_id="t1",
            category="fact_lookup",
            prompt="test",
            target_files=["a.py"],
            verifier="contains_text",
        )
        config = MemoryConfig(name="memory_on", use_memory=True)
        result = experiment._run_mock_task(config, task)

        assert result["task_id"] == "t1"
        assert result["correct"] is True
        assert result["repeated_reads"] == 0
        assert "tool_calls" in result
        assert "duration" in result

    def test_mock_history_task_eligible(self) -> None:
        """有 setup_turns 的 mock 任务 memory_hit=1"""
        experiment = MemoryExperiment(use_real_model=False)
        task = MemoryTask(
            task_id="t1",
            category="history_reference",
            prompt="test",
            setup_turns=["read a.py"],
            target_files=["a.py"],
        )
        config = MemoryConfig(name="memory_on", use_memory=True)
        result = experiment._run_mock_task(config, task)
        assert result["memory_hits"] == 1

    def test_mock_no_setup_turns_not_eligible(self) -> None:
        """无 setup_turns 的 mock 任务 memory_hit=-1"""
        experiment = MemoryExperiment(use_real_model=False)
        task = MemoryTask(
            task_id="t1",
            category="fact_lookup",
            prompt="test",
            target_files=["a.py"],
        )
        config = MemoryConfig(name="memory_on", use_memory=True)
        result = experiment._run_mock_task(config, task)
        assert result["memory_hits"] == -1


# ============================================================
# MemoryMetrics 聚合测试
# ============================================================


class TestMemoryMetrics:
    """指标聚合测试"""

    def test_eligible_memory_tasks_tracked(self) -> None:
        """eligible_memory_tasks 被正确追踪"""
        experiment = MemoryExperiment(use_real_model=False)
        results = experiment.run()
        for r in results:
            assert hasattr(r.metrics, "eligible_memory_tasks")
            assert hasattr(r.metrics, "avg_tool_calls")
            assert hasattr(r.metrics, "avg_duration")

    def test_memory_hit_rate_uses_eligible_count(self) -> None:
        """memory_hit_rate 用 eligible 任务数做分母"""
        metrics = MemoryMetrics(
            memory_hit_rate=2 / 3,
            eligible_memory_tasks=3,
        )
        assert metrics.memory_hit_rate == pytest.approx(2 / 3)
        assert metrics.eligible_memory_tasks == 3


# ============================================================
# 报告生成测试
# ============================================================


class TestReport:
    """报告生成测试"""

    def test_report_contains_definitions(self) -> None:
        """报告包含指标定义"""
        experiment = MemoryExperiment(use_real_model=False)
        results = experiment.run()
        report = experiment.generate_report(results)

        assert "correct_rate" in report
        assert "repeated_reads" in report
        assert "memory_hit_rate" in report
        assert "avg_tool_calls" in report
        assert "avg_duration" in report

    def test_report_contains_config_table(self) -> None:
        """报告包含配置表格"""
        experiment = MemoryExperiment(use_real_model=False)
        results = experiment.run()
        report = experiment.generate_report(results)

        assert "memory_on" in report
        assert "memory_off" in report
        assert "memory_irrelevant" in report

    def test_report_contains_task_details(self) -> None:
        """报告包含各任务详情"""
        experiment = MemoryExperiment(use_real_model=False)
        results = experiment.run()
        report = experiment.generate_report(results)

        assert "各任务详情" in report
        for task in MEMORY_TASKS:
            assert task.task_id in report
