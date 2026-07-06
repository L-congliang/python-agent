"""Smoke test: memory_on with 4 L3/L4 tasks."""
from dotenv import load_dotenv
load_dotenv()

from agent.evaluation.memory_experiment import MemoryExperiment, MemoryConfig, MEMORY_TASKS

tasks = [t for t in MEMORY_TASKS if t.dependency_level in ("L3", "L4")][:4]
exp = MemoryExperiment(use_real_model=True)
result = exp._run_single_config(
    MemoryConfig(name="memory_on", use_memory=True),
    tasks,
)
exp.save_report([result], filename="smoke-memory_on.md")
print(result.config.name, result.is_abnormal, result.abnormal_count, result.metrics.memory_dependent_success_rate)
