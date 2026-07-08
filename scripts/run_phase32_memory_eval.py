#!/usr/bin/env python3
"""Phase 3.2E Memory Evaluation Runner

专用 memory 评测 runner，输出 memory_on / memory_off / memory_irrelevant 三组对比。
适合 before/after 对比，区分主效果指标和诊断指标。

用法：
    uv run python scripts/run_phase32_memory_eval.py
    uv run python scripts/run_phase32_memory_eval.py --output-dir .agent/eval
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加 src 到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.evaluation.memory_experiment import MemoryExperiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3.2E Memory Evaluation Runner")
    parser.add_argument(
        "--output-dir",
        default=".agent/eval",
        help="输出目录（默认 .agent/eval）",
    )
    parser.add_argument(
        "--with-reflection",
        action="store_true",
        default=False,
        help="启用 reflection retry（Phase 3.2C）",
    )
    parser.add_argument(
        "--three-group",
        action="store_true",
        default=False,
        help="三组对比：baseline / scripted retry / prompt-sensitive retry（Phase 3.2F）",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"memory_eval_{timestamp}"

    # Phase 3.2C: reflection 配置
    reflection_config = None
    if args.with_reflection:
        from agent.reflection.types import ReflectionConfig
        reflection_config = ReflectionConfig(
            enabled=True,
            max_reflections_per_task=1,
            only_on_failure=True,
            enable_on_reread=True,
            enable_on_high_tool_calls=True,
            tool_call_threshold=5,
        )

    print(f"Phase 3.2E Memory Evaluation Runner")
    print(f"Run ID: {run_id}")
    print(f"Output: {output_dir}")
    print(f"Reflection: {'enabled' if reflection_config else 'disabled'}")
    print()

    # 运行实验（use_real_model=False → ScriptedModelClient + 真实 AgentLoop）
    experiment = MemoryExperiment(
        output_dir=output_dir,
        max_turns=15,
        use_real_model=False,
    )

    # Phase 3.2F: 三组对比模式
    if args.three_group:
        from agent.reflection.types import ReflectionConfig
        from agent.evaluation.memory_experiment import MEMORY_TASKS, MemoryConfig

        # 找 reflection-sensitive 子集（有 retry_branches 的任务）
        subset = [t for t in MEMORY_TASKS if t.retry_branches is not None]
        if not subset:
            print("ERROR: No tasks with retry_branches found. Cannot run three-group comparison.")
            return

        print(f"Three-group comparison on {len(subset)} reflection-sensitive tasks")
        print(f"Tasks: {[t.task_id for t in subset]}")
        print()

        reflection_config = ReflectionConfig(
            enabled=True,
            max_reflections_per_task=1,
            only_on_failure=True,
            enable_on_reread=True,
            enable_on_high_tool_calls=True,
            tool_call_threshold=5,
        )

        # Group 1: Subset Baseline（memory_off，无 retry）
        print("Running Subset Baseline (memory_off, no retry)...")
        baseline_config_off = MemoryConfig(name="subset_baseline", use_memory=False)
        baseline_result = experiment._run_single_config(baseline_config_off, subset)

        # Group 2: Subset Scripted Retry（memory_off + 固定 retry_script）
        # 关键：临时关闭 retry_branches，只保留 retry_script
        # 这样 _run_scripted_task 会走 ScriptedModelClient（固定路径），
        # 而不是 PromptAwareScriptedModelClient（prompt-sensitive 路径）
        print("Running Subset Scripted Retry (memory_off, fixed retry)...")
        saved_branches: dict[str, dict] = {}
        for t in subset:
            saved_branches[t.task_id] = {
                "retry_branches": t.retry_branches,
                "retry_script": t.retry_script,
            }
            if t.retry_branches and t.default_retry_branch in t.retry_branches:
                t.retry_script = t.retry_branches[t.default_retry_branch]
                t.retry_branches = None  # 关键：关闭 prompt-sensitive 路径
        scripted_config = MemoryConfig(name="subset_scripted_retry", use_memory=False)
        scripted_result = experiment._run_single_config(scripted_config, subset, reflection_config)
        # 恢复
        for t in subset:
            saved = saved_branches[t.task_id]
            t.retry_branches = saved["retry_branches"]
            t.retry_script = saved["retry_script"]

        # Group 3: Subset Prompt-Sensitive Retry（memory_off + prompt-sensitive）
        print("Running Subset Prompt-Sensitive Retry (memory_off, prompt-sensitive)...")
        sensitive_config = MemoryConfig(name="subset_prompt_sensitive", use_memory=False)
        sensitive_result = experiment._run_single_config(sensitive_config, subset, reflection_config)

        results = [baseline_result, scripted_result, sensitive_result]

        # 打印三组对比摘要
        print()
        print("=" * 70)
        print("THREE-GROUP COMPARISON (Phase 3.2F)")
        print("=" * 70)
        print()
        print(f"{'Group':<30} {'correct':>10} {'reread':>10} {'no_reread':>10} {'tools':>8}")
        print("-" * 68)
        for r in results:
            m = r.metrics
            print(
                f"{r.config.name:<30} "
                f"{m.correct_rate:>9.0%} "
                f"{m.target_reread_rate:>9.0%} "
                f"{m.answer_without_reread_rate:>9.0%} "
                f"{m.avg_tool_calls:>7.1f}"
            )

        # Delta 分析
        b = baseline_result.metrics
        s = scripted_result.metrics
        p = sensitive_result.metrics
        print()
        print("Delta Analysis:")
        print(f"  Scripted vs Baseline:   correct {s.correct_rate - b.correct_rate:+.0%}  reread {s.target_reread_rate - b.target_reread_rate:+.0%}")
        print(f"  Prompt-Sens vs Scripted: correct {p.correct_rate - s.correct_rate:+.0%}  reread {p.target_reread_rate - s.target_reread_rate:+.0%}")
        print(f"  Prompt-Sens vs Baseline: correct {p.correct_rate - b.correct_rate:+.0%}  reread {p.target_reread_rate - b.target_reread_rate:+.0%}")

    else:
        print("Running memory ablation experiment...")
        results = experiment.run(reflection_config=reflection_config)

    # 构建 JSON 输出
    from agent.evaluation.memory_experiment import MEMORY_TASKS
    output = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "task_count": len(MEMORY_TASKS),
        "memory": {},
    }

    # 三组模式：记录 task scope 和 delta
    if args.three_group:
        output["task_scope"] = "reflection_sensitive_subset"
        output["subset_task_count"] = len(subset)
        output["subset_task_ids"] = [t.task_id for t in subset]

    for r in results:
        m = r.metrics
        config_data = {
            "correct_rate": m.correct_rate,
            "memory_dependent_success_rate": m.memory_dependent_success_rate,
            "target_reread_rate": m.target_reread_rate,
            "answer_without_reread_rate": m.answer_without_reread_rate,
            "avg_tool_calls": m.avg_tool_calls,
            "avg_duration": m.avg_duration,
            "memory_hit_rate": m.memory_hit_rate,
            "repeated_reads": m.repeated_reads,
            "eligible_memory_tasks": m.eligible_memory_tasks,
            "l3l4_tasks": m.l3l4_tasks,
            "l3l4_correct": m.l3l4_correct,
            "is_abnormal": r.is_abnormal,
            "abnormal_count": r.abnormal_count,
        }
        # 添加 reflection 指标（--with-reflection 时始终输出，保证 schema 稳定）
        if reflection_config is not None:
            config_data["reflection_trigger_rate"] = m.reflection_trigger_rate
            config_data["reflection_retry_success_rate"] = m.reflection_retry_success_rate
            config_data["reflection_avg_extra_tool_calls"] = m.reflection_avg_extra_tool_calls
            config_data["reflection_helped_tasks"] = m.reflection_helped_tasks
        output["memory"][r.config.name] = config_data

    # 三组模式：写入 delta 指标
    if args.three_group and len(results) >= 3:
        b = results[0].metrics  # subset_baseline
        s = results[1].metrics  # subset_scripted_retry
        p = results[2].metrics  # subset_prompt_sensitive
        output["comparison"] = {
            "scripted_vs_baseline": {
                "correct_delta": s.correct_rate - b.correct_rate,
                "reread_delta": s.target_reread_rate - b.target_reread_rate,
                "no_reread_delta": s.answer_without_reread_rate - b.answer_without_reread_rate,
                "tools_delta": s.avg_tool_calls - b.avg_tool_calls,
            },
            "prompt_sensitive_vs_scripted": {
                "correct_delta": p.correct_rate - s.correct_rate,
                "reread_delta": p.target_reread_rate - s.target_reread_rate,
                "no_reread_delta": p.answer_without_reread_rate - s.answer_without_reread_rate,
                "tools_delta": p.avg_tool_calls - s.avg_tool_calls,
            },
            "prompt_sensitive_vs_baseline": {
                "correct_delta": p.correct_rate - b.correct_rate,
                "reread_delta": p.target_reread_rate - b.target_reread_rate,
                "no_reread_delta": p.answer_without_reread_rate - b.answer_without_reread_rate,
                "tools_delta": p.avg_tool_calls - b.avg_tool_calls,
            },
        }

    # 写 JSON
    json_path = output_dir / f"{run_id}.json"
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"JSON: {json_path}")

    # 写 Markdown 报告
    report = experiment.generate_report(results)
    md_path = output_dir / f"{run_id}.md"
    md_path.write_text(report, encoding="utf-8")
    print(f"Markdown: {md_path}")

    # 打印摘要
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    # 主效果指标表
    print()
    print("Primary Effect Metrics (主效果指标):")
    print(f"{'Config':<20} {'correct':>10} {'mem_dep':>10} {'reread':>10} {'no_reread':>10} {'tools':>8} {'dur':>8}")
    print("-" * 76)
    for r in results:
        m = r.metrics
        print(
            f"{r.config.name:<20} "
            f"{m.correct_rate:>9.0%} "
            f"{m.memory_dependent_success_rate:>9.0%} "
            f"{m.target_reread_rate:>9.0%} "
            f"{m.answer_without_reread_rate:>9.0%} "
            f"{m.avg_tool_calls:>7.1f} "
            f"{m.avg_duration:>7.1f}s"
        )

    # 诊断指标表
    print()
    print("Diagnostic Metrics (诊断指标，不作为主结论):")
    print(f"{'Config':<20} {'mem_hit':>10} {'rereads':>10}")
    print("-" * 40)
    for r in results:
        m = r.metrics
        print(f"{r.config.name:<20} {m.memory_hit_rate:>9.0%} {m.repeated_reads:>10}")

    # Reflection 指标表（如果有）
    has_reflection = any(r.metrics.reflection_trigger_rate > 0 for r in results)
    if has_reflection:
        print()
        print("Reflection Metrics (Phase 3.2C):")
        print(f"{'Config':<20} {'trig_rate':>10} {'retry_ok':>10} {'helped':>8} {'extra_tools':>12}")
        print("-" * 60)
        for r in results:
            m = r.metrics
            print(
                f"{r.config.name:<20} "
                f"{m.reflection_trigger_rate:>9.0%} "
                f"{m.reflection_retry_success_rate:>9.0%} "
                f"{m.reflection_helped_tasks:>7d} "
                f"{m.reflection_avg_extra_tool_calls:>11.1f}"
            )

    # 差异分析
    if len(results) >= 2:
        on = next((r for r in results if r.config.name == "memory_on"), None)
        off = next((r for r in results if r.config.name == "memory_off"), None)
        if on and off:
            print()
            print("Key Differences (memory_on vs memory_off):")
            m_on, m_off = on.metrics, off.metrics

            tool_diff = m_on.avg_tool_calls - m_off.avg_tool_calls
            reread_diff = m_on.target_reread_rate - m_off.target_reread_rate
            correct_diff = m_on.correct_rate - m_off.correct_rate

            print(f"  avg_tool_calls: {tool_diff:+.1f} ({'memory_on 更省' if tool_diff < 0 else 'memory_off 更省' if tool_diff > 0 else '无差异'})")
            print(f"  target_reread_rate: {reread_diff:+.0%} ({'memory_on 更少 reread' if reread_diff < 0 else '无差异' if reread_diff == 0 else 'memory_on 更多 reread'})")
            print(f"  correct_rate: {correct_diff:+.0%}")

            if tool_diff == 0 and reread_diff == 0 and correct_diff == 0:
                print()
                print("  NOTE: 当前任务集在 FakeModelClient 下未观察到差异。")
                print("  升级条件：如需验证真实差异，设置 RUN_REAL_MEMORY_EVAL=1 运行 real-model eval。")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
