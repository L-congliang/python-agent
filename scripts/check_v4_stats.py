"""Check V4 task statistics."""
from agent.evaluation.memory_experiment import MEMORY_TASKS
from collections import Counter

# 依赖等级分布
dep_counts = Counter(t.dependency_level for t in MEMORY_TASKS)
print('=== 依赖等级分布 ===')
for level in ['L1', 'L2', 'L3', 'L4']:
    count = dep_counts.get(level, 0)
    print(f'  {level}: {count}')

# verifier 分布
verifier_counts = Counter(t.verifier for t in MEMORY_TASKS)
print('\n=== Verifier 分布 ===')
for v, c in verifier_counts.most_common():
    print(f'  {v}: {c}')

# forbidden_reads 统计
forbidden_count = sum(1 for t in MEMORY_TASKS if t.forbidden_reads)
print(f'\n=== forbidden_reads: {forbidden_count} 个任务 ===')

# allowed_files + no_extra_changes 统计
strict_count = sum(1 for t in MEMORY_TASKS if t.allowed_files and t.no_extra_changes)
print(f'=== allowed_files + no_extra_changes: {strict_count} 个任务 ===')

# 噪声任务
noise_count = sum(1 for t in MEMORY_TASKS if t.category == 'noise')
print(f'=== noise 类别: {noise_count} 个任务 ===')

# L3/L4 占比
l3l4 = dep_counts.get('L3', 0) + dep_counts.get('L4', 0)
total = len(MEMORY_TASKS)
print(f'\n=== L3/L4 占比: {l3l4}/{total} = {l3l4/total:.1%} ===')
