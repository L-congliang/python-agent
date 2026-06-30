"""自动指标计算和回归对比。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from pathlib import Path

from agent.evaluation.evaluator import EvalResult


@dataclass
class Metrics:
    """评测指标汇总。"""

    total_tasks: int
    passed: int
    pass_rate: float
    avg_attempts: float
    avg_tool_steps: float
    by_category: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class RegressionReport:
    """回归对比报告。"""

    baseline_run_id: str
    current_run_id: str
    baseline_pass_rate: float
    current_pass_rate: float
    pass_rate_delta: float
    improved_tasks: list[str]
    regressed_tasks: list[str]
    unchanged_tasks: list[str]


def aggregate_results(results: list[EvalResult]) -> Metrics:
    """从评测结果列表计算汇总指标。"""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    pass_rate = passed / total if total > 0 else 0.0

    avg_attempts = (
        sum(r.attempts for r in results) / total if total > 0 else 0.0
    )
    avg_tool_steps = (
        sum(r.tool_steps for r in results) / total if total > 0 else 0.0
    )

    # 按类别统计
    by_category: dict[str, dict[str, Any]] = {}
    for r in results:
        cat = r.category
        if cat not in by_category:
            by_category[cat] = {"passed": 0, "total": 0, "failure_categories": {}}
        by_category[cat]["total"] += 1
        if r.passed:
            by_category[cat]["passed"] += 1
        else:
            # 统计失败类别
            fail_cat = _classify_failure(r)
            fails = by_category[cat]["failure_categories"]
            fails[fail_cat] = fails.get(fail_cat, 0) + 1

    # 计算每个类别的 pass_rate
    for cat_data in by_category.values():
        t = cat_data["total"]
        p = cat_data["passed"]
        cat_data["rate"] = p / t if t > 0 else 0.0

    return Metrics(
        total_tasks=total,
        passed=passed,
        pass_rate=pass_rate,
        avg_attempts=avg_attempts,
        avg_tool_steps=avg_tool_steps,
        by_category=by_category,
    )


def _classify_failure(result: EvalResult) -> str:
    """将失败结果分类为具体原因。"""
    if result.error:
        if "timed out" in result.error.lower():
            return "timeout"
        if "verifier" in result.error.lower():
            return "wrong_answer"
    if result.stop_reason == "step_limit_reached":
        return "step_limit"
    if result.stop_reason == "retry_limit_reached":
        return "retry_limit"
    if result.stop_reason == "model_output_exhausted":
        return "model_error"
    return "unknown"


def save_results(
    results: list[EvalResult],
    metrics: Metrics,
    run_id: str,
    output_dir: str | Path,
) -> Path:
    """保存评测结果到 JSON 文件。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{run_id}.json"

    data = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "total_tasks": metrics.total_tasks,
        "passed": metrics.passed,
        "pass_rate": metrics.pass_rate,
        "avg_attempts": metrics.avg_attempts,
        "avg_tool_steps": metrics.avg_tool_steps,
        "by_category": metrics.by_category,
        "tasks": [
            {
                "id": r.task_id,
                "passed": r.passed,
                "attempts": r.attempts,
                "tool_steps": r.tool_steps,
                "category": r.category,
                "stop_reason": r.stop_reason,
                "error": r.error,
            }
            for r in results
        ],
    }

    output_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_file


def load_results(path: str | Path) -> dict[str, Any]:
    """加载之前保存的评测结果。"""
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def compare_results(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> RegressionReport:
    """对比两组评测结果，生成回归报告。"""
    baseline_tasks = {t["id"]: t for t in baseline.get("tasks", [])}
    current_tasks = {t["id"]: t for t in current.get("tasks", [])}

    improved: list[str] = []
    regressed: list[str] = []
    unchanged: list[str] = []

    for task_id in current_tasks:
        if task_id not in baseline_tasks:
            continue
        was_pass = baseline_tasks[task_id].get("passed", False)
        now_pass = current_tasks[task_id].get("passed", False)
        if not was_pass and now_pass:
            improved.append(task_id)
        elif was_pass and not now_pass:
            regressed.append(task_id)
        else:
            unchanged.append(task_id)

    baseline_rate = baseline.get("pass_rate", 0.0)
    current_rate = current.get("pass_rate", 0.0)

    return RegressionReport(
        baseline_run_id=baseline.get("run_id", "unknown"),
        current_run_id=current.get("run_id", "unknown"),
        baseline_pass_rate=baseline_rate,
        current_pass_rate=current_rate,
        pass_rate_delta=current_rate - baseline_rate,
        improved_tasks=improved,
        regressed_tasks=regressed,
        unchanged_tasks=unchanged,
    )


def format_report(report: RegressionReport) -> str:
    """将回归报告格式化为可读文本。"""
    lines = [
        f"Regression Report: {report.baseline_run_id} -> {report.current_run_id}",
        f"  Pass rate: {report.baseline_pass_rate:.1%} -> {report.current_pass_rate:.1%} "
        f"({report.pass_rate_delta:+.1%})",
        "",
    ]

    if report.improved_tasks:
        lines.append(f"  Improved ({len(report.improved_tasks)}):")
        for t in report.improved_tasks:
            lines.append(f"    + {t}")

    if report.regressed_tasks:
        lines.append(f"  Regressed ({len(report.regressed_tasks)}):")
        for t in report.regressed_tasks:
            lines.append(f"    - {t}")

    if report.unchanged_tasks:
        lines.append(f"  Unchanged ({len(report.unchanged_tasks)}):")
        for t in report.unchanged_tasks:
            lines.append(f"    = {t}")

    return "\n".join(lines)
