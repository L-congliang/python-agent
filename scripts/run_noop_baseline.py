"""No-op Baseline Runner — 验证 benchmark verifier 不会产生 false positive。

运行 benchmark tasks，但 agent 不做任何操作（直接返回固定文本）。
期望结果：所有任务的 pass rate 应为 0%。

用法:
    uv run python scripts/run_noop_baseline.py
    uv run python scripts/run_noop_baseline.py --benchmark benchmarks/coding_tasks_v2.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# 确保 src 在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.evaluation.benchmark import load_benchmark
from agent.evaluation.evaluator import Evaluator
from agent.evaluation.metrics import aggregate_results, save_results


class NoOpModelClient:
    """No-op 模型客户端：每次都返回固定文本，不触发任何工具调用。

    用于验证 benchmark verifier 不会产生 false positive。
    如果 no-op agent 也能通过某个 task，说明该 task 的 verifier 有漏洞。
    """

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.supports_prompt_cache: bool = False
        self.last_completion_metadata: dict = {}

    def chat_stream(self, messages: list[dict], system: str = "", **kwargs):  # type: ignore[type-arg]
        """返回固定文本，不包含任何工具调用。"""
        from agent.core.model import StreamResult

        prompt = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                prompt = str(msg.get("content", ""))
                break
        self.prompts.append(prompt)

        text = "I have completed the task."
        return StreamResult(
            text=iter([text]),
            content_blocks=[{"type": "text", "text": text}],
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    def complete(self, prompt: str, max_new_tokens: int, **kwargs: object) -> str:
        self.prompts.append(prompt)
        return "I have completed the task."


def run_noop_baseline(benchmark_path: str = "benchmarks/coding_tasks_v2.json") -> dict:
    """运行 no-op baseline 测试。

    Args:
        benchmark_path: benchmark 文件路径

    Returns:
        结果字典，包含 pass_rate 和每个 task 的详情
    """
    print(f"Loading benchmark: {benchmark_path}")
    tasks = load_benchmark(benchmark_path)
    print(f"Loaded {len(tasks)} tasks")

    client = NoOpModelClient()
    evaluator = Evaluator()

    results = []
    for task in tasks:
        print(f"  Running task: {task.id} ... ", end="", flush=True)
        result = evaluator.run_task(
            task, client,
            fixture_dir=task.fixture_repo if task.fixture_repo else None,
        )
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} (stop_reason={result.stop_reason})")
        results.append(result)

    metrics = aggregate_results(results)

    print("\n" + "=" * 60)
    print("NO-OP BASELINE RESULTS")
    print("=" * 60)
    print(f"Total tasks: {metrics.total_tasks}")
    print(f"Passed: {metrics.passed}")
    print(f"Pass rate: {metrics.pass_rate:.1%}")
    print()

    # 每个 task 的详情
    print("Per-task breakdown:")
    print("-" * 60)
    false_positives = []
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        err = r.error[:60] if r.error else ""
        print(f"  {r.task_id:30s} {status}  error={err}")
        if r.passed:
            false_positives.append(r.task_id)

    print()
    if false_positives:
        print(f"FALSE POSITIVES DETECTED: {len(false_positives)} tasks passed with no-op agent!")
        for fp in false_positives:
            print(f"  - {fp}")
        print("These tasks have broken verifiers that need fixing.")
    else:
        print("No false positives detected. All verifiers are working correctly.")

    return {
        "pass_rate": metrics.pass_rate,
        "total_tasks": metrics.total_tasks,
        "passed": metrics.passed,
        "false_positives": false_positives,
        "details": [
            {"task_id": r.task_id, "passed": r.passed, "error": r.error}
            for r in results
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run no-op baseline to verify benchmark verifiers")
    parser.add_argument(
        "--benchmark",
        default="benchmarks/coding_tasks_v2.json",
        help="Path to benchmark file (default: benchmarks/coding_tasks_v2.json)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file path (optional)",
    )
    args = parser.parse_args()

    result = run_noop_baseline(args.benchmark)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nResults saved to: {output_path}")

    # 返回码：0 = no false positives (good), 1 = has false positives (bad)
    has_fp = len(result["false_positives"]) > 0
    sys.exit(1 if has_fp else 0)


if __name__ == "__main__":
    main()
