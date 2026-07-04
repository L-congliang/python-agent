"""Smoke test: 验证退化任务修复"""
import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from dotenv import load_dotenv
load_dotenv()

from agent.evaluation.memory_experiment import MemoryExperiment, MemoryConfig, MEMORY_TASKS

subset = [t for t in MEMORY_TASKS if t.task_id in ('fact_manager_methods', 'history_loop_config')]
print(f'Tasks: {[t.task_id for t in subset]}')

exp = MemoryExperiment(use_real_model=True, max_turns=10)
config = MemoryConfig(name='memory_on', use_memory=True)
result = exp._run_single_config(config, subset)

m = result.metrics
print(f'\nResults: correct_rate={m.correct_rate:.0%}, repeated_reads={m.repeated_reads}')

for tr in result.task_results:
    print(f'  {tr["task_id"]}: correct={tr["correct"]}, calls={tr["tool_calls"]}, preview={tr.get("result_preview","")[:100]}')
