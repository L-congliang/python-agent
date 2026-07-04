"""Smoke test for new memory tasks."""
from dotenv import load_dotenv
load_dotenv()

from agent.evaluation.memory_experiment import MemoryExperiment, MemoryConfig, MEMORY_TASKS

subset = [t for t in MEMORY_TASKS if t.task_id in ('recall_api_key', 'noise_db_config')]
print(f'Tasks: {[t.task_id for t in subset]}')

exp = MemoryExperiment(use_real_model=True, max_turns=10)
config = MemoryConfig(name='memory_on', use_memory=True)
result = exp._run_single_config(config, subset)

m = result.metrics
print(f'correct_rate: {m.correct_rate:.0%}')
print(f'repeated_reads: {m.repeated_reads}')
print(f'memory_hit_rate: {m.memory_hit_rate:.0%} ({m.eligible_memory_tasks} eligible)')
print(f'avg_tool_calls: {m.avg_tool_calls:.1f}')
print(f'avg_duration: {m.avg_duration:.1f}s')

for tr in result.task_results:
    print(f'  {tr["task_id"]}: correct={tr["correct"]}, reads={tr["repeated_reads"]}, hit={tr["memory_hits"]}, calls={tr["tool_calls"]}')
    print(f'    preview: {tr.get("result_preview", "")[:120]}')
