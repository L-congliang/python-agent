"""对比 V1 和 V2 benchmark 的 no-op baseline 结果"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scripts.run_noop_baseline import run_noop_baseline

print("=== V1 Benchmark (old) ===")
v1 = run_noop_baseline("benchmarks/coding_tasks.json")
print()

print("=== V2 Benchmark (hardened) ===")
v2 = run_noop_baseline("benchmarks/coding_tasks_v2.json")
print()

print("SUMMARY:")
print(f"  V1 no-op pass rate: {v1['pass_rate']:.1%} (false positives: {len(v1['false_positives'])})")
print(f"  V2 no-op pass rate: {v2['pass_rate']:.1%} (false positives: {len(v2['false_positives'])})")
