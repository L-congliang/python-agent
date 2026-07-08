"""No-op Baseline 测试

验证 no-op baseline runner 正确检测 false positive：
1. no-op agent 的 pass rate 应为 0%
2. 如果有 false positive，runner 正确报告
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_noop_baseline import run_noop_baseline, NoOpModelClient


class TestNoOpModelClient:
    """NoOpModelClient 测试"""

    def test_returns_fixed_text(self) -> None:
        client = NoOpModelClient()
        from agent.core.model import StreamResult
        result = client.chat_stream([{"role": "user", "content": "test"}])
        assert isinstance(result, StreamResult)

    def test_records_prompts(self) -> None:
        client = NoOpModelClient()
        client.chat_stream([{"role": "user", "content": "hello"}])
        assert len(client.prompts) == 1

    def test_supports_prompt_cache_false(self) -> None:
        client = NoOpModelClient()
        assert client.supports_prompt_cache is False


class TestNoOpBaseline:
    """No-op baseline 集成测试"""

    def test_noop_baseline_v2(self) -> None:
        """v2 benchmark 的 no-op pass rate 应为 0%"""
        result = run_noop_baseline("benchmarks/coding_tasks_v2.json")
        assert result["pass_rate"] == 0.0, (
            f"No-op baseline pass rate should be 0%, got {result['pass_rate']:.1%}. "
            f"False positives: {result['false_positives']}"
        )

    def test_noop_baseline_reports_false_positives(self) -> None:
        """runner 正确报告 false positive 任务"""
        result = run_noop_baseline("benchmarks/coding_tasks_v2.json")
        # 不应该有 false positive
        assert len(result["false_positives"]) == 0, (
            f"False positives detected: {result['false_positives']}"
        )

    def test_noop_baseline_details_complete(self) -> None:
        """每个 task 都有详情"""
        result = run_noop_baseline("benchmarks/coding_tasks_v2.json")
        assert len(result["details"]) == result["total_tasks"]
        for detail in result["details"]:
            assert "task_id" in detail
            assert "passed" in detail

    def test_noop_baseline_tool_steps_zero(self) -> None:
        """no-op agent 应该没有任何工具调用步骤"""
        from agent.evaluation.benchmark import load_benchmark
        from agent.evaluation.evaluator import Evaluator
        from scripts.run_noop_baseline import NoOpModelClient

        tasks = load_benchmark("benchmarks/coding_tasks_v2.json")
        client = NoOpModelClient()
        evaluator = Evaluator()
        for task in tasks:
            result = evaluator.run_task(task, client)
            assert result.tool_steps == 0, (
                f"Task {task.id}: no-op agent should have 0 tool steps, "
                f"got {result.tool_steps}"
            )
