"""Evaluation Baseline Runner 测试

验证 baseline runner 能收集 memory/recovery/permission 指标，并输出 markdown + json。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from agent.evaluation.metrics import Metrics


# ============================================================
# 辅助函数
# ============================================================


def create_temp_output_dir() -> Path:
    """创建临时输出目录"""
    return Path(tempfile.mkdtemp()) / "eval"


# ============================================================
# Baseline Runner 测试
# ============================================================


class TestBaselineRunner:
    """Baseline Runner 核心功能测试。"""

    def test_runner_can_collect_memory_metrics(self) -> None:
        """runner 能收集 memory 指标"""
        from scripts.run_phase32_baseline import collect_memory_metrics

        metrics = collect_memory_metrics()
        assert metrics is not None
        assert "memory_on" in metrics
        assert "memory_off" in metrics

        # 验证指标字段（来自真实实验，不是硬编码）
        for config_name, config_metrics in metrics.items():
            # 如果有 error，说明实验失败，但不是硬编码
            if "error" in config_metrics:
                continue
            assert "correct_rate" in config_metrics
            assert "avg_tool_calls" in config_metrics
            assert "avg_duration" in config_metrics

    def test_runner_calls_real_memory_experiment(self) -> None:
        """runner 调用真实的 memory_experiment，不是硬编码"""
        from scripts.run_phase32_baseline import collect_memory_metrics
        from unittest.mock import patch, MagicMock

        # Mock MemoryExperiment 来验证它被调用
        with patch("agent.evaluation.memory_experiment.MemoryExperiment") as MockExperiment:
            # 设置 mock 返回值
            mock_result = MagicMock()
            mock_result.config.name = "memory_on"
            mock_result.metrics.correct_rate = 0.85
            mock_result.metrics.memory_hit_rate = 0.70
            mock_result.metrics.memory_dependent_success_rate = 0.80
            mock_result.metrics.target_reread_rate = 0.30
            mock_result.metrics.answer_without_reread_rate = 0.60
            mock_result.metrics.avg_tool_calls = 4.5
            mock_result.metrics.avg_duration = 12.3

            mock_instance = MockExperiment.return_value
            mock_instance.run.return_value = [mock_result]

            # 调用
            metrics = collect_memory_metrics()

            # 验证 MemoryExperiment 被调用
            MockExperiment.assert_called_once_with(use_real_model=False)
            mock_instance.run.assert_called_once()

            # 验证返回值来自 mock
            assert "memory_on" in metrics
            assert metrics["memory_on"]["correct_rate"] == 0.85

    def test_runner_can_collect_recovery_metrics(self) -> None:
        """runner 能收集 recovery 指标（当前是 placeholder）"""
        from scripts.run_phase32_baseline import collect_recovery_metrics

        metrics = collect_recovery_metrics()
        assert metrics is not None
        assert "rollback_success_rate" in metrics
        assert "backup_created_rate" in metrics
        assert "history_recorded_rate" in metrics

        # 当前是 placeholder，不是真实实验
        for key, value in metrics.items():
            assert value == "not_measured", f"{key} should be not_measured, got {value}"

    def test_runner_can_collect_permission_metrics(self) -> None:
        """runner 能收集 permission 指标（当前是 placeholder）"""
        from scripts.run_phase32_baseline import collect_permission_metrics

        metrics = collect_permission_metrics()
        assert metrics is not None
        assert "ask_count" in metrics
        assert "session_allow_hit_rate" in metrics
        assert "deny_preserved_rate" in metrics

        # 当前是 placeholder，不是真实实验
        for key, value in metrics.items():
            assert value == "not_measured", f"{key} should be not_measured, got {value}"

    def test_runner_outputs_markdown_and_json(self) -> None:
        """runner 输出 markdown 和 json"""
        from scripts.run_phase32_baseline import run_baseline

        output_dir = create_temp_output_dir()
        result = run_baseline(output_dir=output_dir)

        assert result is not None
        assert "json_path" in result
        assert "md_path" in result

        # 验证文件存在
        assert Path(result["json_path"]).exists()
        assert Path(result["md_path"]).exists()

        # 验证 json 内容
        with open(result["json_path"], encoding="utf-8") as f:
            data = json.load(f)
        assert "memory" in data
        assert "recovery" in data
        assert "permission" in data

        # 验证 markdown 内容
        md_content = Path(result["md_path"]).read_text(encoding="utf-8")
        assert "Memory Baseline" in md_content
        assert "Recovery Baseline" in md_content
        assert "Permission Baseline" in md_content

    def test_runner_does_not_require_real_api(self) -> None:
        """runner 不依赖真实 API"""
        from scripts.run_phase32_baseline import run_baseline

        # 不设置 MIMO_API_KEY，应该也能运行
        output_dir = create_temp_output_dir()
        result = run_baseline(output_dir=output_dir)

        assert result is not None
        assert Path(result["json_path"]).exists()


# ============================================================
# Metrics Schema 测试
# ============================================================


class TestMetricsSchema:
    """Metrics schema 稳定性测试。"""

    def test_memory_metrics_schema(self) -> None:
        """memory 指标 schema 稳定"""
        from scripts.run_phase32_baseline import collect_memory_metrics

        metrics = collect_memory_metrics()

        # 验证 memory_on 的指标字段
        memory_on = metrics["memory_on"]
        required_fields = [
            "correct_rate",
            "memory_hit_rate",
            "memory_dependent_success_rate",
            "target_reread_rate",
            "avg_tool_calls",
            "avg_duration",
        ]
        for field in required_fields:
            assert field in memory_on, f"Missing field: {field}"

    def test_recovery_metrics_schema(self) -> None:
        """recovery 指标 schema 稳定"""
        from scripts.run_phase32_baseline import collect_recovery_metrics

        metrics = collect_recovery_metrics()

        required_fields = [
            "rollback_success_rate",
            "backup_created_rate",
            "history_recorded_rate",
        ]
        for field in required_fields:
            assert field in metrics, f"Missing field: {field}"

    def test_permission_metrics_schema(self) -> None:
        """permission 指标 schema 稳定"""
        from scripts.run_phase32_baseline import collect_permission_metrics

        metrics = collect_permission_metrics()

        required_fields = [
            "ask_count",
            "session_allow_hit_rate",
            "deny_preserved_rate",
        ]
        for field in required_fields:
            assert field in metrics, f"Missing field: {field}"


# ============================================================
# 边界测试
# ============================================================


class TestBaselineRunnerEdgeCases:
    """边界情况测试。"""

    def test_runner_with_empty_output_dir(self) -> None:
        """输出目录不存在时自动创建"""
        from scripts.run_phase32_baseline import run_baseline

        output_dir = Path(tempfile.mkdtemp()) / "nonexistent" / "eval"
        result = run_baseline(output_dir=output_dir)

        assert result is not None
        assert Path(result["json_path"]).exists()

    def test_runner_output_json_structure(self) -> None:
        """输出 json 结构正确"""
        from scripts.run_phase32_baseline import run_baseline

        output_dir = create_temp_output_dir()
        result = run_baseline(output_dir=output_dir)

        with open(result["json_path"], encoding="utf-8") as f:
            data = json.load(f)

        # 验证顶层结构
        assert "run_id" in data
        assert "timestamp" in data
        assert "memory" in data
        assert "recovery" in data
        assert "permission" in data

    def test_runner_output_markdown_sections(self) -> None:
        """输出 markdown 有正确的 section"""
        from scripts.run_phase32_baseline import run_baseline

        output_dir = create_temp_output_dir()
        result = run_baseline(output_dir=output_dir)

        md_content = Path(result["md_path"]).read_text(encoding="utf-8")

        # 验证 section 标题
        assert "# Phase 3.2A Baseline Report" in md_content
        assert "## Memory Baseline" in md_content
        assert "## Recovery Baseline" in md_content
        assert "## Permission Baseline" in md_content
