"""
评测框架 - Benchmark 定义、执行、指标计算

包含:
- benchmark: Benchmark 任务定义和加载器
- fake_client: FakeModelClient，脚本化模型（确定性测试）
- evaluator: 任务执行器（prompt → agent → 验证结果）
- metrics: 自动指标计算（pass_rate、avg_attempts 等）
- recovery_experiment: Recovery Ablation 实验
"""

from agent.evaluation.benchmark import BenchmarkTask, load_benchmark
from agent.evaluation.fake_client import FakeModelClient
from agent.evaluation.evaluator import Evaluator, EvalResult
from agent.evaluation.metrics import aggregate_results
from agent.evaluation.recovery_experiment import RecoveryExperiment, RecoveryReport

__all__ = [
    "BenchmarkTask",
    "load_benchmark",
    "FakeModelClient",
    "Evaluator",
    "EvalResult",
    "aggregate_results",
    "RecoveryExperiment",
    "RecoveryReport",
]
