"""运行 Benchmark 并输出基线数据。

支持两种模式：
  python benchmarks/run_benchmark.py              # FakeModelClient（确定性测试）
  python benchmarks/run_benchmark.py --real       # 真实 API（端到端测试）
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from agent.evaluation.benchmark import load_benchmark
from agent.evaluation.evaluator import Evaluator
from agent.evaluation.fake_client import FakeModelClient
from agent.evaluation.metrics import aggregate_results, save_results


def create_client(real: bool = False) -> FakeModelClient | object:
    """创建模型客户端。"""
    if not real:
        return FakeModelClient(["<final>Done</final>"])

    # 真实 API 客户端
    from agent.core.model import MimoClient, ModelConfig

    api_key = os.environ.get("MIMO_API_KEY", "")
    base_url = os.environ.get(
        "MIMO_BASE_URL",
        "https://token-plan-cn.xiaomimimo.com/anthropic",
    )
    model = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")

    if not api_key:
        raise ValueError(
            "MIMO_API_KEY not set. Export it or pass via environment."
        )

    config = ModelConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    return MimoClient(config)


def run_benchmark(
    benchmark_path: str = "benchmarks/coding_tasks.json",
    output_dir: str = "benchmarks/results",
    run_id: str = "baseline",
    real: bool = False,
) -> None:
    """运行 benchmark 并输出结果。"""
    print(f"Mode: {'REAL API' if real else 'FakeModelClient'}")
    print(f"Loading benchmark from: {benchmark_path}")
    tasks = load_benchmark(benchmark_path)
    print(f"Loaded {len(tasks)} tasks\n")

    evaluator = Evaluator(max_tool_calls=10)
    client = create_client(real=real)
    results = []

    for i, task in enumerate(tasks, 1):
        print(f"  [{i}/{len(tasks)}] {task.id} ({task.category})...", end=" ")

        # 真实 API 需要为每个任务创建新的客户端（保持状态隔离）
        task_client = client if not real else create_client(real=True)

        try:
            result = evaluator.run_task(
                task,
                task_client,
                fixture_dir=task.fixture_repo if task.fixture_repo else None,
            )
        except Exception as e:
            from agent.evaluation.evaluator import EvalResult
            result = EvalResult(
                task_id=task.id,
                passed=False,
                attempts=0,
                tool_steps=0,
                category=task.category,
                stop_reason="error",
                error=str(e)[:200],
            )

        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} (attempts={result.attempts}, steps={result.tool_steps})")
        if result.error:
            print(f"    error: {result.error[:100]}")

    # 计算指标
    metrics = aggregate_results(results)

    # 输出摘要
    print("\n" + "=" * 50)
    print(f"Benchmark Results: {run_id}")
    print("=" * 50)
    print(f"  Total tasks: {metrics.total_tasks}")
    print(f"  Passed: {metrics.passed}/{metrics.total_tasks} ({metrics.pass_rate:.1%})")
    print(f"  Avg attempts: {metrics.avg_attempts:.1f}")
    print(f"  Avg tool steps: {metrics.avg_tool_steps:.1f}")

    print("\n  By category:")
    for cat, data in metrics.by_category.items():
        print(f"    {cat}: {data['passed']}/{data['total']} ({data['rate']:.1%})")

    # 保存结果
    output_path = save_results(results, metrics, run_id, output_dir)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run benchmark")
    parser.add_argument(
        "--real", action="store_true",
        help="Use real API (MimoClient) instead of FakeModelClient",
    )
    parser.add_argument(
        "--run-id", default="baseline",
        help="Run ID for result file (default: baseline)",
    )
    args = parser.parse_args()

    run_id = "real-baseline" if args.real else "baseline"
    run_benchmark(run_id=args.run_id or run_id, real=args.real)
