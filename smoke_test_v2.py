"""V2 Smoke Test - 单轮验证新任务"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from agent.evaluation.memory_experiment import MemoryExperiment

print("=== V2 SMOKE TEST (1 round) ===")
experiment = MemoryExperiment(use_real_model=True)
results = experiment.run()

print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)

for r in results:
    m = r.metrics
    print(f"\n{r.config.name}:")
    print(f"  correct_rate: {m.correct_rate:.0%}")
    print(f"  repeated_reads: {m.repeated_reads}")
    print(f"  memory_hit_rate: {m.memory_hit_rate:.0%} ({m.eligible_memory_tasks} eligible)")
    print(f"  avg_tool_calls: {m.avg_tool_calls:.1f}")
    print(f"  avg_duration: {m.avg_duration:.1f}s")

print("\n=== TASK DETAILS ===")
for r in results:
    print(f"\n{r.config.name}:")
    for tr in r.task_results:
        correct = "OK" if tr.get("correct") else "FAIL"
        print(f"  {tr['task_id']:40s} {correct:4s} tool_calls={tr.get('tool_calls', 0)}")
