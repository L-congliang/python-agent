"""评测框架测试。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from agent.evaluation.benchmark import BenchmarkTask, load_benchmark
from agent.evaluation.fake_client import FakeModelClient
from agent.evaluation.evaluator import Evaluator, EvalResult, StepRecord
from agent.evaluation.metrics import (
    Metrics,
    RegressionReport,
    aggregate_results,
    save_results,
    load_results,
    compare_results,
    format_report,
)


# ============================================================
# BenchmarkTask + load_benchmark 测试
# ============================================================


class TestBenchmarkTask:
    """BenchmarkTask 数据类测试。"""

    def test_create_task(self) -> None:
        task = BenchmarkTask(
            id="test",
            prompt="do something",
            fixture_repo="fixture",
            allowed_tools=["read"],
            step_budget=4,
            expected_artifact="file.txt",
            verifier="assert True",
            category="test",
        )
        assert task.id == "test"
        assert task.prompt == "do something"
        assert task.step_budget == 4
        assert task.setup is None

    def test_create_task_with_setup(self) -> None:
        task = BenchmarkTask(
            id="test",
            prompt="do something",
            fixture_repo="fixture",
            allowed_tools=["read"],
            step_budget=4,
            expected_artifact="file.txt",
            verifier="assert True",
            category="test",
            setup={"history_count": 12},
        )
        assert task.setup == {"history_count": 12}


class TestLoadBenchmark:
    """load_benchmark 加载器测试。"""

    def test_load_valid_benchmark(self, tmp_path: Path) -> None:
        data = {
            "schema_version": 1,
            "tasks": [
                {
                    "id": "task1",
                    "prompt": "test prompt",
                    "allowed_tools": ["read"],
                    "step_budget": 4,
                    "verifier": "assert True",
                    "category": "test",
                }
            ],
        }
        file = tmp_path / "benchmark.json"
        file.write_text(json.dumps(data), encoding="utf-8")

        tasks = load_benchmark(file)
        assert len(tasks) == 1
        assert tasks[0].id == "task1"

    def test_load_missing_tasks_key(self, tmp_path: Path) -> None:
        file = tmp_path / "benchmark.json"
        file.write_text('{"schema_version": 1}', encoding="utf-8")

        with pytest.raises(ValueError, match="missing 'tasks' key"):
            load_benchmark(file)

    def test_load_missing_required_field(self, tmp_path: Path) -> None:
        data = {
            "tasks": [
                {
                    "id": "task1",
                    "prompt": "test",
                    # missing required fields
                }
            ],
        }
        file = tmp_path / "benchmark.json"
        file.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="missing required fields"):
            load_benchmark(file)

    def test_load_multiple_tasks(self, tmp_path: Path) -> None:
        data = {
            "tasks": [
                {
                    "id": f"task{i}",
                    "prompt": f"prompt {i}",
                    "allowed_tools": ["read"],
                    "step_budget": 4,
                    "verifier": "assert True",
                    "category": "test",
                }
                for i in range(5)
            ],
        }
        file = tmp_path / "benchmark.json"
        file.write_text(json.dumps(data), encoding="utf-8")

        tasks = load_benchmark(file)
        assert len(tasks) == 5
        assert [t.id for t in tasks] == [f"task{i}" for i in range(5)]


# ============================================================
# FakeModelClient 测试
# ============================================================


class TestFakeModelClient:
    """FakeModelClient 脚本化模型测试。"""

    def test_deterministic_output(self) -> None:
        client = FakeModelClient(["output1", "output2"])
        assert client.complete("prompt1", 100) == "output1"
        assert client.complete("prompt2", 100) == "output2"

    def test_records_prompts(self) -> None:
        client = FakeModelClient(["out1", "out2"])
        client.complete("prompt1", 100)
        client.complete("prompt2", 100)
        assert client.prompts == ["prompt1", "prompt2"]

    def test_exhausted_raises_error(self) -> None:
        client = FakeModelClient([])
        with pytest.raises(RuntimeError, match="exhausted"):
            client.complete("prompt", 100)

    def test_single_output(self) -> None:
        client = FakeModelClient(["only_one"])
        assert client.complete("prompt", 100) == "only_one"
        with pytest.raises(RuntimeError):
            client.complete("prompt", 100)

    def test_supports_prompt_cache_false(self) -> None:
        client = FakeModelClient(["out"])
        assert client.supports_prompt_cache is False


# ============================================================
# Evaluator 测试
# ============================================================


class TestEvaluator:
    """Evaluator 任务执行器测试。"""

    def test_run_task_returns_result(self, tmp_path: Path) -> None:
        task = BenchmarkTask(
            id="test_task",
            prompt="test prompt",
            fixture_repo="",
            allowed_tools=["read"],
            step_budget=4,
            expected_artifact="",
            verifier="",
            category="test",
        )
        client = FakeModelClient(["<final>Done.</final>"])
        evaluator = Evaluator()
        result = evaluator.run_task(task, client)

        assert isinstance(result, EvalResult)
        assert result.task_id == "test_task"
        assert result.category == "test"

    def test_run_task_with_final_answer(self, tmp_path: Path) -> None:
        task = BenchmarkTask(
            id="test",
            prompt="test",
            fixture_repo="",
            allowed_tools=[],
            step_budget=4,
            expected_artifact="",
            verifier="",
            category="test",
        )
        client = FakeModelClient(["<final>Answer</final>"])
        evaluator = Evaluator()
        result = evaluator.run_task(task, client)

        assert result.stop_reason == "final_answer_returned"

    def test_run_task_with_tool_call(self, tmp_path: Path) -> None:
        """测试 FakeModelClient 返回工具调用时，AgentLoop 能处理。"""
        fixture_dir = tmp_path / "fixture"
        fixture_dir.mkdir()
        (fixture_dir / "test.txt").write_text("hello world")

        task = BenchmarkTask(
            id="test",
            prompt="edit file",
            fixture_repo="",
            allowed_tools=["file_edit"],
            step_budget=4,
            expected_artifact="",
            verifier="",
            category="test",
        )
        # FakeModelClient 返回文本（FakeAdapter 不解析工具调用）
        client = FakeModelClient(["I see the file says 'hello world'.", "<final>Done</final>"])
        evaluator = Evaluator()
        result = evaluator.run_task(task, client, fixture_dir=fixture_dir)

        # AgentLoop 成功执行，返回 final answer
        assert result.stop_reason == "final_answer_returned"
        assert result.attempts >= 1

    def test_run_task_exhausts_output(self, tmp_path: Path) -> None:
        """测试 FakeModelClient 输出用完时，AgentLoop 抛出异常。"""
        task = BenchmarkTask(
            id="test",
            prompt="test",
            fixture_repo="",
            allowed_tools=[],
            step_budget=4,
            expected_artifact="",
            verifier="",
            category="test",
        )
        client = FakeModelClient([])  # 空输出
        evaluator = Evaluator()
        result = evaluator.run_task(task, client)

        # AgentLoop 抛出 RuntimeError，被 evaluator 捕获
        assert "error" in result.stop_reason.lower()

    def test_step_records_created(self, tmp_path: Path) -> None:
        """测试 Evaluator 记录执行步骤。"""
        task = BenchmarkTask(
            id="test",
            prompt="test",
            fixture_repo="",
            allowed_tools=[],
            step_budget=4,
            expected_artifact="",
            verifier="",
            category="test",
        )
        client = FakeModelClient(["<final>Done</final>"])
        evaluator = Evaluator()
        result = evaluator.run_task(task, client)

        assert len(result.steps) >= 1
        # AgentLoop 执行后记录 final_answer 步骤
        assert result.steps[0].action == "final_answer"


# ============================================================
# Metrics 测试
# ============================================================


class TestMetrics:
    """Metrics 指标计算测试。"""

    def test_aggregate_all_pass(self) -> None:
        results = [
            EvalResult("t1", True, 1, 2, "edit"),
            EvalResult("t2", True, 1, 1, "edit"),
        ]
        metrics = aggregate_results(results)
        assert metrics.total_tasks == 2
        assert metrics.passed == 2
        assert metrics.pass_rate == 1.0

    def test_aggregate_mixed(self) -> None:
        results = [
            EvalResult("t1", True, 1, 2, "edit"),
            EvalResult("t2", False, 2, 3, "search", stop_reason="step_limit"),
        ]
        metrics = aggregate_results(results)
        assert metrics.total_tasks == 2
        assert metrics.passed == 1
        assert metrics.pass_rate == 0.5

    def test_aggregate_by_category(self) -> None:
        results = [
            EvalResult("t1", True, 1, 1, "edit"),
            EvalResult("t2", True, 1, 1, "edit"),
            EvalResult("t3", False, 1, 1, "search"),
        ]
        metrics = aggregate_results(results)
        assert metrics.by_category["edit"]["passed"] == 2
        assert metrics.by_category["edit"]["total"] == 2
        assert metrics.by_category["edit"]["rate"] == 1.0
        assert metrics.by_category["search"]["passed"] == 0
        assert metrics.by_category["search"]["total"] == 1
        assert metrics.by_category["search"]["rate"] == 0.0

    def test_aggregate_empty(self) -> None:
        metrics = aggregate_results([])
        assert metrics.total_tasks == 0
        assert metrics.pass_rate == 0.0

    def test_failure_classification(self) -> None:
        results = [
            EvalResult("t1", False, 1, 1, "test", stop_reason="step_limit_reached"),
            EvalResult("t2", False, 1, 1, "test", stop_reason="retry_limit_reached"),
            EvalResult("t3", False, 1, 1, "test", error="Verifier timed out"),
        ]
        metrics = aggregate_results(results)
        fails = metrics.by_category["test"]["failure_categories"]
        assert fails.get("step_limit", 0) == 1
        assert fails.get("retry_limit", 0) == 1
        assert fails.get("timeout", 0) == 1


# ============================================================
# Regression 对比测试
# ============================================================


class TestRegression:
    """回归对比测试。"""

    def test_compare_improved(self) -> None:
        baseline = {
            "run_id": "v1",
            "pass_rate": 0.5,
            "tasks": [
                {"id": "t1", "passed": False},
                {"id": "t2", "passed": True},
            ],
        }
        current = {
            "run_id": "v2",
            "pass_rate": 1.0,
            "tasks": [
                {"id": "t1", "passed": True},
                {"id": "t2", "passed": True},
            ],
        }
        report = compare_results(baseline, current)
        assert report.pass_rate_delta == 0.5
        assert "t1" in report.improved_tasks
        assert "t2" in report.unchanged_tasks

    def test_compare_regressed(self) -> None:
        baseline = {
            "run_id": "v1",
            "pass_rate": 1.0,
            "tasks": [{"id": "t1", "passed": True}],
        }
        current = {
            "run_id": "v2",
            "pass_rate": 0.0,
            "tasks": [{"id": "t1", "passed": False}],
        }
        report = compare_results(baseline, current)
        assert report.pass_rate_delta == -1.0
        assert "t1" in report.regressed_tasks

    def test_format_report(self) -> None:
        report = RegressionReport(
            baseline_run_id="v1",
            current_run_id="v2",
            baseline_pass_rate=0.7,
            current_pass_rate=0.8,
            pass_rate_delta=0.1,
            improved_tasks=["t1"],
            regressed_tasks=[],
            unchanged_tasks=["t2"],
        )
        text = format_report(report)
        assert "70.0%" in text
        assert "80.0%" in text
        assert "+10.0%" in text
        assert "t1" in text

    def test_save_and_load_results(self, tmp_path: Path) -> None:
        results = [EvalResult("t1", True, 1, 1, "test")]
        metrics = aggregate_results(results)

        output_dir = tmp_path / "results"
        save_results(results, metrics, "run_001", output_dir)

        loaded = load_results(output_dir / "run_001.json")
        assert loaded["run_id"] == "run_001"
        assert loaded["pass_rate"] == 1.0
        assert len(loaded["tasks"]) == 1
