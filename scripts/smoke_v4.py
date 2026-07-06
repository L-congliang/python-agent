"""Smoke test: V4 L3/L4 tasks with memory_on."""
from dotenv import load_dotenv
load_dotenv()

from agent.evaluation.memory_experiment import MemoryExperiment, MemoryConfig, MEMORY_TASKS

# 只跑 V4 新增的 6 个任务
v4_task_ids = [
    "delayed_dual_constant_edit",
    "conflict_secret_disambiguation_strict",
    "cross_file_literal_bundle_no_reread",
    "resume_multi_edit_after_irrelevant_round",
    "constraint_then_edit_single_target",
    "forbidden_reread_multi_fact_answer",
]
tasks = [t for t in MEMORY_TASKS if t.task_id in v4_task_ids]

print(f"=== V4 Smoke Test: {len(tasks)} tasks ===")
for t in tasks:
    print(f"  {t.task_id}: {t.dependency_level} {t.verifier}")

exp = MemoryExperiment(use_real_model=True)
result = exp._run_single_config(
    MemoryConfig(name="memory_on", use_memory=True),
    tasks,
)
exp.save_report([result], filename="smoke-v4.md")

print(f"\n=== 结果 ===")
print(f"is_abnormal: {result.is_abnormal}")
print(f"abnormal_count: {result.abnormal_count}")
print(f"correct_rate: {result.metrics.correct_rate:.2%}")
