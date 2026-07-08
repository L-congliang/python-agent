"""V2 正式量化实验 - 5 轮 × 3 组 × 18 任务（异常感知版）"""

import json
import os
import sys
import time
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from agent.evaluation.memory_experiment import MemoryExperiment, MEMORY_TASKS


def run_one_round(round_num: int) -> dict:
    """跑一轮实验（3 个 config）"""
    print(f"\n{'='*60}", flush=True)
    print(f"ROUND {round_num} START", flush=True)
    print(f"{'='*60}", flush=True)

    experiment = MemoryExperiment(use_real_model=True)
    results = experiment.run()

    round_data = {}
    for r in results:
        m = r.metrics
        config_name = r.config.name
        round_data[config_name] = {
            "correct_rate": m.correct_rate,
            "repeated_reads": m.repeated_reads,
            "memory_hit_rate": m.memory_hit_rate,
            "eligible_memory_tasks": m.eligible_memory_tasks,
            "avg_tool_calls": m.avg_tool_calls,
            "avg_duration": m.avg_duration,
            "total_duration": r.duration,
            "task_results": r.task_results,
            "is_abnormal": r.is_abnormal,
            "abnormal_count": r.abnormal_count,
        }
        abnormal_flag = f" [ABNORMAL: {r.abnormal_count} tasks]" if r.is_abnormal else ""
        print(f"\n{config_name}{abnormal_flag}:", flush=True)
        print(f"  correct_rate: {m.correct_rate:.0%}", flush=True)
        print(f"  repeated_reads: {m.repeated_reads}", flush=True)
        print(f"  memory_hit_rate: {m.memory_hit_rate:.0%} ({m.eligible_memory_tasks} eligible)", flush=True)
        print(f"  avg_tool_calls: {m.avg_tool_calls:.1f}", flush=True)
        print(f"  avg_duration: {m.avg_duration:.1f}s", flush=True)

    print(f"\nROUND {round_num} DONE", flush=True)
    return round_data


def compute_stats(values: list[float]) -> dict:
    """计算 mean/min/max/range/std"""
    if not values:
        return {"mean": 0, "min": 0, "max": 0, "range": 0, "std": 0}
    mean = statistics.mean(values)
    return {
        "mean": mean,
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
        "std": statistics.stdev(values) if len(values) > 1 else 0,
    }


def main():
    NUM_ROUNDS = 5
    all_rounds = []
    anomalies = []

    for round_num in range(1, NUM_ROUNDS + 1):
        try:
            round_data = run_one_round(round_num)
            all_rounds.append({"round": round_num, "data": round_data, "anomaly": False})
        except Exception as e:
            print(f"\n!!! ROUND {round_num} ANOMALY: {e}", flush=True)
            anomalies.append({"round": round_num, "error": str(e)})
            all_rounds.append({"round": round_num, "data": {}, "anomaly": True})

        if round_num < NUM_ROUNDS:
            print(f"\nWaiting 60s before round {round_num + 1}...", flush=True)
            time.sleep(60)

    # 汇总（只统计正常 config）
    print(f"\n{'='*60}", flush=True)
    print("AGGREGATE RESULTS (only normal configs)", flush=True)
    print(f"{'='*60}", flush=True)

    configs = ["memory_on", "memory_off", "memory_irrelevant"]
    metrics_keys = ["correct_rate", "repeated_reads", "memory_hit_rate", "avg_tool_calls", "avg_duration"]

    aggregate = {}
    for config in configs:
        aggregate[config] = {}
        for metric in metrics_keys:
            # 只统计正常 config（is_abnormal=False）
            values = [
                r["data"][config][metric]
                for r in all_rounds
                if not r["anomaly"] and config in r["data"] and not r["data"][config].get("is_abnormal", False)
            ]
            aggregate[config][metric] = compute_stats(values)

    # 打印汇总表
    for metric in metrics_keys:
        print(f"\n--- {metric} ---", flush=True)
        print(f"{'config':<20} {'mean':>8} {'min':>8} {'max':>8} {'range':>8} {'std':>8} {'n':>4}", flush=True)
        for config in configs:
            s = aggregate[config][metric]
            # 统计正常轮次数
            n = len([
                r for r in all_rounds
                if not r["anomaly"] and config in r["data"] and not r["data"][config].get("is_abnormal", False)
            ])
            fmt = ".0%" if metric in ("correct_rate", "memory_hit_rate") else ".1f"
            print(f"{config:<20} {s['mean']:>8{fmt}} {s['min']:>8{fmt}} {s['max']:>8{fmt}} {s['range']:>8{fmt}} {s['std']:>8{fmt}} {n:>4}", flush=True)

    # 统计异常轮次
    print(f"\n--- ANOMALY SUMMARY ---", flush=True)
    for config in configs:
        abnormal_rounds = [
            r["round"] for r in all_rounds
            if not r["anomaly"] and config in r["data"] and r["data"][config].get("is_abnormal", False)
        ]
        if abnormal_rounds:
            print(f"{config}: {len(abnormal_rounds)} abnormal rounds: {abnormal_rounds}", flush=True)
        else:
            print(f"{config}: no abnormal rounds", flush=True)

    # 保存完整数据
    output = {
        "commit_id": os.popen("git rev-parse HEAD").read().strip(),
        "model": os.environ.get("MIMO_MODEL", "mimo-v2.5-pro"),
        "num_rounds": NUM_ROUNDS,
        "num_tasks": len(MEMORY_TASKS),
        "anomalies": anomalies,
        "rounds": all_rounds,
        "aggregate": aggregate,
    }

    output_path = Path("docs/test-reports/formal-experiment-v2-final-raw.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nRaw data saved to: {output_path}", flush=True)

    return output


if __name__ == "__main__":
    main()
