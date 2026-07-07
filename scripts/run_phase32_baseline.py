#!/usr/bin/env python
"""Phase 3.2A Baseline Runner

统一 baseline evaluation 入口，收集 memory/recovery/permission 指标。

使用方式:
    uv run python scripts/run_phase32_baseline.py
    uv run python scripts/run_phase32_baseline.py --output-dir .agent/eval

输出:
    - .agent/eval/{run_id}.json
    - .agent/eval/{run_id}.md
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.evaluation.metrics import Metrics

logger = logging.getLogger("scripts.run_phase32_baseline")


# ============================================================
# Memory Baseline
# ============================================================


def collect_memory_metrics() -> dict[str, dict[str, float]]:
    """收集 memory baseline 指标

    调用真实的 memory_experiment.py，使用 FakeModelClient。

    Returns:
        memory 指标字典，key 是配置名称（memory_on / memory_off）
    """
    try:
        from agent.evaluation.memory_experiment import MemoryExperiment

        logger.info("Running memory experiment with FakeModelClient...")
        experiment = MemoryExperiment(use_real_model=False)
        results = experiment.run()

        # 提取指标
        metrics = {}
        for r in results:
            config_name = r.config.name
            m = r.metrics
            metrics[config_name] = {
                "correct_rate": m.correct_rate,
                "memory_hit_rate": m.memory_hit_rate,
                "memory_dependent_success_rate": m.memory_dependent_success_rate,
                "target_reread_rate": m.target_reread_rate,
                "answer_without_reread_rate": m.answer_without_reread_rate,
                "avg_tool_calls": m.avg_tool_calls,
                "avg_duration": m.avg_duration,
            }

        logger.info("Memory experiment completed: %d configs", len(metrics))
        return metrics

    except Exception as e:
        logger.error("Memory experiment failed: %s", e)
        # 返回 placeholder
        return {
            "memory_on": {"error": str(e)},
            "memory_off": {"error": str(e)},
        }


# ============================================================
# Recovery Baseline
# ============================================================


def collect_recovery_metrics() -> dict[str, float]:
    """收集 recovery baseline 指标

    当前 recovery_experiment.py 需要真实 API，暂时返回 placeholder。

    Returns:
        recovery 指标字典
    """
    logger.warning("Recovery baseline not yet implemented with FakeModelClient")
    return {
        "rollback_success_rate": "not_measured",
        "backup_created_rate": "not_measured",
        "history_recorded_rate": "not_measured",
    }


# ============================================================
# Permission Baseline
# ============================================================


def collect_permission_metrics() -> dict[str, float]:
    """收集 permission baseline 指标

    当前 security_experiment.py 需要真实 API，暂时返回 placeholder。

    Returns:
        permission 指标字典
    """
    logger.warning("Permission baseline not yet implemented with FakeModelClient")
    return {
        "ask_count": "not_measured",
        "session_allow_hit_rate": "not_measured",
        "deny_preserved_rate": "not_measured",
    }


# ============================================================
# Baseline Runner
# ============================================================


def run_baseline(
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """运行 baseline evaluation

    Args:
        output_dir: 输出目录，默认 .agent/eval

    Returns:
        结果字典，包含 json_path 和 md_path
    """
    if output_dir is None:
        output_dir = Path(".agent/eval")

    output_dir.mkdir(parents=True, exist_ok=True)

    # 收集指标
    logger.info("Collecting memory metrics...")
    memory_metrics = collect_memory_metrics()

    logger.info("Collecting recovery metrics...")
    recovery_metrics = collect_recovery_metrics()

    logger.info("Collecting permission metrics...")
    permission_metrics = collect_permission_metrics()

    # 生成 run_id
    run_id = f"phase32_baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 构建结果数据
    result_data = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "memory": memory_metrics,
        "recovery": recovery_metrics,
        "permission": permission_metrics,
    }

    # 保存 JSON
    json_path = output_dir / f"{run_id}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    logger.info("JSON saved: %s", json_path)

    # 生成 Markdown
    md_path = output_dir / f"{run_id}.md"
    md_content = generate_markdown_report(result_data)
    md_path.write_text(md_content, encoding="utf-8")
    logger.info("Markdown saved: %s", md_path)

    return {
        "run_id": run_id,
        "json_path": str(json_path),
        "md_path": str(md_path),
    }


def generate_markdown_report(data: dict[str, Any]) -> str:
    """生成 Markdown 报告

    Args:
        data: 结果数据

    Returns:
        Markdown 内容
    """
    lines = [
        "# Phase 3.2A Baseline Report",
        "",
        f"**Run ID:** {data['run_id']}",
        f"**Timestamp:** {data['timestamp']}",
        "",
        "## Memory Baseline",
        "",
        "| Metric | memory_on | memory_off | Delta |",
        "|--------|-----------|------------|-------|",
    ]

    # Memory 指标
    memory_on = data["memory"]["memory_on"]
    memory_off = data["memory"]["memory_off"]

    # 检查是否有 error
    if "error" in memory_on:
        lines.append(f"| error | {memory_on['error']} | - | - |")
    else:
        for key in memory_on:
            val_on = memory_on[key]
            val_off = memory_off[key]
            if isinstance(val_on, (int, float)) and isinstance(val_off, (int, float)):
                delta = val_on - val_off
                lines.append(f"| {key} | {val_on:.2f} | {val_off:.2f} | {delta:+.2f} |")
            else:
                lines.append(f"| {key} | {val_on} | {val_off} | - |")

    lines.extend([
        "",
        "## Recovery Baseline",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ])

    # Recovery 指标
    for key, value in data["recovery"].items():
        if value == "not_measured":
            lines.append(f"| {key} | ⚠️ not measured |")
        else:
            lines.append(f"| {key} | {value:.2f} |")

    lines.extend([
        "",
        "## Permission Baseline",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ])

    # Permission 指标
    for key, value in data["permission"].items():
        if value == "not_measured":
            lines.append(f"| {key} | ⚠️ not measured |")
        else:
            lines.append(f"| {key} | {value:.2f} |")

    lines.extend([
        "",
        "---",
        "",
        "*This report is generated by Phase 3.2A Baseline Runner.*",
        "",
        "## Notes",
        "",
        "- Memory baseline uses FakeModelClient (no real API required)",
        "- Recovery and Permission baselines are placeholder (not_measured)",
        "- Phase 3.2A goal: establish runner, schema, and output format",
        "- Phase 3.2B+ will replace placeholder with real experiment data",
    ])

    return "\n".join(lines)


# ============================================================
# CLI 入口
# ============================================================


def main() -> None:
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Phase 3.2A Baseline Runner")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="输出目录，默认 .agent/eval",
    )
    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s: %(message)s",
    )

    # 运行 baseline
    output_dir = Path(args.output_dir) if args.output_dir else None
    result = run_baseline(output_dir=output_dir)

    print(f"\nBaseline completed:")
    print(f"  Run ID: {result['run_id']}")
    print(f"  JSON: {result['json_path']}")
    print(f"  Markdown: {result['md_path']}")


if __name__ == "__main__":
    main()
