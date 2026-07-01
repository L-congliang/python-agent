"""Recovery Ablation 实验测试"""

import json
from pathlib import Path

import pytest

from agent.evaluation.recovery_experiment import (
    RecoveryExperiment,
    RecoveryReport,
    RecoveryScenario,
    RECOVERY_SCENARIOS,
)


class TestRecoveryExperiment:
    """RecoveryExperiment 测试"""

    def test_run_experiment(self, tmp_path: Path) -> None:
        """运行实验"""
        experiment = RecoveryExperiment(tmp_path)
        report = experiment.run()

        assert report.total_scenarios == 10
        assert len(report.resume_enabled_results) == 10
        assert len(report.resume_disabled_results) == 10

    def test_metrics_calculation(self, tmp_path: Path) -> None:
        """计算指标"""
        experiment = RecoveryExperiment(tmp_path)
        report = experiment.run()

        assert "resume_success_rate" in report.metrics
        assert "stale_reanchor_rate" in report.metrics
        assert "workspace_drift_detection_rate" in report.metrics
        assert "resume_false_accept_rate" in report.metrics
        assert "enabled_success_rate" in report.metrics
        assert "disabled_success_rate" in report.metrics

    def test_format_report(self, tmp_path: Path) -> None:
        """格式化报告"""
        experiment = RecoveryExperiment(tmp_path)
        report = experiment.run()
        formatted = experiment.format_report(report)

        assert "Recovery Ablation 实验报告" in formatted
        assert "resume_enabled" in formatted
        assert "resume_disabled" in formatted

    def test_scenario_count(self) -> None:
        """场景数量正确"""
        assert len(RECOVERY_SCENARIOS) == 10

    def test_scenario_names_unique(self) -> None:
        """场景名称唯一"""
        names = [s.name for s in RECOVERY_SCENARIOS]
        assert len(names) == len(set(names))


class TestRecoveryScenario:
    """RecoveryScenario 测试"""

    def test_scenario_attributes(self) -> None:
        """场景属性正确"""
        scenario = RECOVERY_SCENARIOS[0]
        assert scenario.name == "checkpoint_resume"
        assert "正常恢复" in scenario.description
        assert scenario.expected_status == "full-valid"

    def test_scenario_setup_is_valid_json(self) -> None:
        """场景 setup 是有效的 JSON"""
        for scenario in RECOVERY_SCENARIOS:
            data = json.loads(scenario.setup)
            assert "action" in data


class TestRecoveryReport:
    """RecoveryReport 测试"""

    def test_report_attributes(self, tmp_path: Path) -> None:
        """报告属性正确"""
        experiment = RecoveryExperiment(tmp_path)
        report = experiment.run()

        assert isinstance(report, RecoveryReport)
        assert report.total_scenarios == 10
        assert isinstance(report.metrics, dict)
