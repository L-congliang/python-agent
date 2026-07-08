"""Verifier for fix_negative_discount task.

Tests:
1. Normal discount works correctly (100 with 20% = 80)
2. Negative discount raises ValueError
3. Zero discount works (100 with 0% = 100)
"""
import sys
import math

sys.path.insert(0, ".")
from broken import calculate_discount

# Test 1: Normal discount
result = calculate_discount(100.0, 20.0)
assert math.isclose(result, 80.0, rel_tol=1e-9), f"Normal discount failed: expected 80.0, got {result}"

# Test 2: Zero discount
result = calculate_discount(100.0, 0.0)
assert math.isclose(result, 100.0, rel_tol=1e-9), f"Zero discount failed: expected 100.0, got {result}"

# Test 3: Negative discount must raise ValueError
try:
    calculate_discount(100.0, -10.0)
    assert False, "ValueError not raised for negative discount (-10.0)"
except ValueError:
    pass  # Expected

# Test 4: Another negative discount
try:
    calculate_discount(50.0, -5.0)
    assert False, "ValueError not raised for negative discount (-5.0)"
except ValueError:
    pass  # Expected

print("All checks passed")
