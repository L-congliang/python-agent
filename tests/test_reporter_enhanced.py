"""增强版 Reporter 测试

验证 reporter 新增字段的正确性：
1. permission 记录
2. 文件读/写追踪
3. 聚合指标计算
4. summary.md 生成
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from agent.observability.reporter import RunReporter


class TestReporterEnhancedFields:
    """测试增强字段"""

    def test_record_permission(self, tmp_path: Path) -> None:
        """权限决策正确记录"""
        reporter = RunReporter(tmp_path)
        reporter.record_permission("ask")
        reporter.record_permission("allow")
        reporter.record_permission("allow")
        reporter.record_permission("deny")

        report = reporter.report
        assert report["permission_asks"] == 1
        assert report["permission_allows"] == 2
        assert report["permission_denies"] == 1

    def test_record_tool_call_with_enhanced_fields(self, tmp_path: Path) -> None:
        """工具调用记录包含增强字段"""
        reporter = RunReporter(tmp_path)
        reporter.record_tool_call(
            tool_name="edit",
            tool_args={"file_path": "main.py", "old_string": "x", "new_string": "y"},
            duration_ms=100,
            is_error=False,
            turn_index=1,
            permission_decision="allow",
            files_read=["main.py"],
            files_written=["main.py"],
            bytes_read=50,
            bytes_written=55,
        )

        report = reporter.report
        tc = report["tool_calls"][0]
        assert tc["name"] == "edit"
        assert tc["turn_index"] == 1
        assert tc["permission_decision"] == "allow"
        assert tc["files_read"] == ["main.py"]
        assert tc["files_written"] == ["main.py"]
        assert tc["bytes_read"] == 50
        assert tc["bytes_written"] == 55
        assert "input_summary" in tc

    def test_bytes_accumulation(self, tmp_path: Path) -> None:
        """字节数正确累加"""
        reporter = RunReporter(tmp_path)
        reporter.record_tool_call(
            tool_name="read", tool_args={}, duration_ms=10, is_error=False,
            bytes_read=100,
        )
        reporter.record_tool_call(
            tool_name="write", tool_args={}, duration_ms=20, is_error=False,
            bytes_written=200,
        )

        report = reporter.report
        assert report["total_bytes_read"] == 100
        assert report["total_bytes_written"] == 200

    def test_files_tracked(self, tmp_path: Path) -> None:
        """读/写文件列表正确追踪"""
        reporter = RunReporter(tmp_path)
        reporter.record_tool_call(
            tool_name="read", tool_args={}, duration_ms=10, is_error=False,
            files_read=["a.py", "b.py"],
        )
        reporter.record_tool_call(
            tool_name="write", tool_args={}, duration_ms=20, is_error=False,
            files_written=["c.py"],
        )

        report = reporter.report
        assert set(report["files_read"]) == {"a.py", "b.py"}
        assert report["files_written"] == ["c.py"]

    def test_set_run_metadata(self, tmp_path: Path) -> None:
        """运行级别元数据正确设置"""
        reporter = RunReporter(tmp_path)
        reporter.set_run_metadata(
            task_id="test_task_001",
            model="mimo-v2.5-pro",
            provider="xiaomi",
        )

        report = reporter.report
        assert report["task_id"] == "test_task_001"
        assert report["model"] == "mimo-v2.5-pro"
        assert report["provider"] == "xiaomi"


class TestAggregates:
    """测试聚合指标"""

    def test_aggregates_with_no_tools(self, tmp_path: Path) -> None:
        """无工具调用时聚合指标正确"""
        reporter = RunReporter(tmp_path)
        reporter.record_start("test")
        reporter.record_finish("completed")

        report = reporter.report
        agg = report["aggregate"]
        assert agg["tool_success_rate"] == 1.0
        assert agg["tool_failure_count"] == 0
        assert agg["p50_latency_ms"] == 0

    def test_aggregates_computed(self, tmp_path: Path) -> None:
        """聚合指标正确计算"""
        reporter = RunReporter(tmp_path)
        reporter.record_start("test")

        # 3 successful + 1 failed
        for i in range(3):
            reporter.record_tool_call(
                tool_name="read", tool_args={}, duration_ms=10 * (i + 1), is_error=False,
            )
        reporter.record_tool_call(
            tool_name="edit", tool_args={}, duration_ms=50, is_error=True,
        )

        reporter.record_permission("allow")
        reporter.record_permission("allow")
        reporter.record_permission("deny")

        reporter.record_finish("completed")

        report = reporter.report
        agg = report["aggregate"]
        assert agg["tool_success_rate"] == 0.75  # 3/4
        assert agg["tool_failure_count"] == 1
        assert agg["p50_latency_ms"] > 0
        assert agg["p95_latency_ms"] > 0
        assert agg["permission_allow_rate"] == pytest.approx(2 / 3, abs=0.001)
        assert agg["permission_deny_count"] == 1

    def test_latency_percentiles(self, tmp_path: Path) -> None:
        """延迟百分位正确计算"""
        reporter = RunReporter(tmp_path)
        reporter.record_start("test")

        latencies = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        for lat in latencies:
            reporter.record_tool_call(
                tool_name="read", tool_args={}, duration_ms=lat, is_error=False,
            )

        reporter.record_finish("completed")

        agg = reporter.report["aggregate"]
        assert agg["p50_latency_ms"] == 50  # 50th percentile
        assert agg["max_latency_ms"] == 100


class TestSummaryMarkdown:
    """测试 Markdown 摘要生成"""

    def test_generate_summary(self, tmp_path: Path) -> None:
        """生成的 Markdown 包含所有关键字段"""
        reporter = RunReporter(tmp_path)
        reporter.record_start("test task")
        reporter.record_tool_call(
            tool_name="read", tool_args={"file_path": "main.py"},
            duration_ms=50, is_error=False, bytes_read=100,
        )
        reporter.record_finish("completed", final_answer="done")

        md = reporter.generate_summary_markdown()
        assert "Run Summary" in md
        assert "Tool Metrics" in md
        assert "File Metrics" in md
        assert "Permission Metrics" in md
        assert "Tool Success Rate" in md
        assert "P50 Latency" in md

    def test_summary_file_written(self, tmp_path: Path) -> None:
        """summary.md 可以写入文件"""
        reporter = RunReporter(tmp_path)
        reporter.record_start("test")
        reporter.record_finish("completed")

        md = reporter.generate_summary_markdown()
        summary_path = tmp_path / "summary.md"
        summary_path.write_text(md, encoding="utf-8")
        assert summary_path.exists()
        content = summary_path.read_text(encoding="utf-8")
        assert "Run Summary" in content


class TestReportJsonStructure:
    """测试 report.json 结构稳定性"""

    def test_report_has_all_new_fields(self, tmp_path: Path) -> None:
        """report 包含所有新增字段"""
        reporter = RunReporter(tmp_path)
        reporter.record_start("test")
        reporter.record_finish("completed")

        report = reporter.report
        # 新增字段
        assert "task_id" in report
        assert "model" in report
        assert "provider" in report
        assert "files_read" in report
        assert "files_written" in report
        assert "total_bytes_read" in report
        assert "total_bytes_written" in report
        assert "total_artifacts" in report
        assert "permission_asks" in report
        assert "permission_allows" in report
        assert "permission_denies" in report
        assert "aggregate" in report

    def test_aggregate_has_required_fields(self, tmp_path: Path) -> None:
        """aggregate 包含所有必需字段"""
        reporter = RunReporter(tmp_path)
        reporter.record_start("test")
        reporter.record_finish("completed")

        agg = reporter.report["aggregate"]
        required = [
            "tool_success_rate", "tool_failure_count",
            "p50_latency_ms", "p95_latency_ms", "max_latency_ms",
            "permission_allow_rate", "permission_deny_count",
        ]
        for field in required:
            assert field in agg, f"Missing aggregate field: {field}"
