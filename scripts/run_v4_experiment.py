"""V4 正式实验：单 config 跑 5 轮，只用 V4 新增的 6 个高难度任务。

用法:
    uv run python scripts/run_v4_experiment.py --config memory_on --rounds 5
    uv run python scripts/run_v4_experiment.py --config memory_off --rounds 5
"""
import argparse
import time

from dotenv import load_dotenv
load_dotenv()

from agent.evaluation.memory_experiment import MemoryExperiment, MemoryConfig, MEMORY_TASKS

# V4 新增的 6 个高难度任务
V4_TASK_IDS = [
    "delayed_dual_constant_edit",
    "conflict_secret_disambiguation_strict",
    "cross_file_literal_bundle_no_reread",
    "resume_multi_edit_after_irrelevant_round",
    "constraint_then_edit_single_target",
    "forbidden_reread_multi_fact_answer",
]

CONFIGS = {
    "memory_on": MemoryConfig(name="memory_on", use_memory=True),
    "memory_off": MemoryConfig(name="memory_off", use_memory=False),
}


def main():
    parser = argparse.ArgumentParser(description="Run V4 memory experiment")
    parser.add_argument("--config", required=True, choices=CONFIGS.keys(), help="Config to run")
    parser.add_argument("--rounds", type=int, default=5, help="Number of rounds")
    parser.add_argument("--delay", type=int, default=60, help="Delay between rounds (seconds)")
    args = parser.parse_args()

    config = CONFIGS[args.config]
    tasks = [t for t in MEMORY_TASKS if t.task_id in V4_TASK_IDS]
    exp = MemoryExperiment(use_real_model=True)

    print(f"=== V4 实验: {config.name} x {args.rounds} 轮 ===")
    print(f"任务数: {len(tasks)}, 轮间延迟: {args.delay}s")
    for t in tasks:
        print(f"  - {t.task_id}: {t.dependency_level} {t.verifier}")
    print()

    results = []
    for i in range(1, args.rounds + 1):
        print(f"--- Round {i}/{args.rounds} ---")
        try:
            result = exp._run_single_config(config, tasks)
            results.append(result)

            # 保存单轮报告
            filename = f"P2-memory-v4-{config.name}-round{i}.md"
            exp.save_report([result], filename=filename)

            # 打印关键指标
            m = result.metrics
            print(f"  is_abnormal: {result.is_abnormal}")
            print(f"  abnormal_count: {result.abnormal_count}")
            print(f"  correct_rate: {m.correct_rate:.2%}")
            print()

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append(None)

        # 轮间延迟
        if i < args.rounds:
            print(f"  等待 {args.delay}s...")
            time.sleep(args.delay)

    # 汇总
    print(f"\n=== {config.name} 汇总 ===")
    clean = [r for r in results if r and not r.is_abnormal]
    abnormal = [r for r in results if r and r.is_abnormal]
    errors = [r for r in results if r is None]
    print(f"总轮次: {len(results)}, Clean: {len(clean)}, Abnormal: {len(abnormal)}, Error: {len(errors)}")

    if clean:
        avg_correct = sum(r.metrics.correct_rate for r in clean) / len(clean)
        print(f"Clean 轮次平均 correct_rate: {avg_correct:.2%}")


if __name__ == "__main__":
    main()
