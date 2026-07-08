"""Verify task list and count"""
import sys
sys.path.insert(0, 'src')
from agent.evaluation.memory_experiment import MEMORY_TASKS

print(f'Total tasks: {len(MEMORY_TASKS)}')
for t in MEMORY_TASKS:
    print(f'  {t.task_id:40s} {t.category:20s} verifier={t.verifier}')
