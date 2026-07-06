"""正式实验脚本：单 config 跑 N 轮。

用法:
    uv run python scripts/run_formal_experiment.py --config memory_on --rounds 5
    uv run python scripts/run_formal_experiment.py --config memory_off --rounds 5
    uv run python scripts/run_formal_experiment.py --config memory_irrelevant --rounds 5
"""
import argparse
import sys
import time

from dotenv import load_dotenv
load_dotenv()

from agent.evaluation.memory_experiment import MemoryExperiment, MemoryConfig, MEMORY_TASKS


CONFIGS = {
    "memory_on": MemoryConfig(name="memory_on", use_memory=True),
    "memory_off": MemoryConfig(name="memory_off", use_memory=False),
    "memory_irrelevant": MemoryConfig(name="memory_irrelevant", use_memory=True, use_irrelevant_memory=True),
}


def main():
    parser = argparse.ArgumentParser(description="Run formal memory experiment")
    parser.add_argument("--config", required=True, choices=CONFIGS.keys(), help="Config to run")
    parser.add_argument("--rounds", type=int, default=5, help="Number of rounds")
    parser.add_argument("--delay", type=int, default=60, help="Delay between rounds (seconds)")
    args = parser.parse_args()

    config = CONFIGS[args.config]
    exp = MemoryExperiment(use_real_model=True)

    print(f"=== 正式实验: {config.name} x {args.rounds} 轮 ===")
    print(f"任务数: {len(MEMORY_TASKS)}, 轮间延迟: {args.delay}s")
    print()

    results = []
    for i in range(1, args.rounds + 1):
        print(f"--- Round {i}/{args.rounds} ---")
        try:
            result = exp._run_single_config(config, MEMORY_TASKS)
            results.append(result)

            # 保存单轮报告
            filename = f"P2-memory-v2-{config.name}-round{i}.md"
            exp.save_report([result], filename=filename)

            # 打印关键指标
            m = result.metrics
            print(f"  is_abnormal: {result.is_abnormal}")
            print(f"  abnormal_count: {result.abnormal_count}")
            print(f"  correct_rate: {m.correct_rate:.2%}")
            print(f"  memory_dependent_success_rate: {m.memory_dependent_success_rate:.2%}")
            print(f"  target_reread_rate: {m.target_reread_rate:.2%}")
            print(f"  answer_without_reread_rate: {m.answer_without_reread_rate:.2%}")
            print(f"  avg_tool_calls: {m.avg_tool_calls:.1f}")
            print(f"  avg_duration: {m.avg_duration:.1f}s")
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
        avg_mdsr = sum(r.metrics.memory_dependent_success_rate for r in clean) / len(clean)
        avg_reread = sum(r.metrics.target_reread_rate for r in clean) / len(clean)
        print(f"Clean 轮次平均:")
        print(f"  correct_rate: {avg_correct:.2%}")
        print(f"  memory_dependent_success_rate: {avg_mdsr:.2%}")
        print(f"  target_reread_rate: {avg_reread:.2%}")


if __name__ == "__main__":
    main()
