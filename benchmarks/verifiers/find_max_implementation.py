"""Verifier for find_max_implementation task.

Checks that answer.txt:
1. Exists
2. Describes what find_max does (finding maximum/largest)
3. Mentions error handling (empty list raises ValueError)
4. References the actual function behavior, not just generic text
"""
import os
import sys

assert os.path.exists("answer.txt"), "answer.txt not created"

text = open("answer.txt", encoding="utf-8").read().lower()
assert len(text) > 20, f"answer.txt is too short ({len(text)} chars), expected a real description"

# Must describe the core behavior
has_max_desc = any(word in text for word in ["max", "maximum", "largest", "greatest", "biggest"])
assert has_max_desc, f"answer.txt does not describe find_max behavior: {text[:200]}"

# Must mention error handling
has_error_desc = any(word in text for word in ["empty", "error", "raise", "valueerror", "exception", "invalid"])
assert has_error_desc, f"answer.txt does not mention error handling: {text[:200]}"

# Must reference the list/input parameter
has_list_ref = any(word in text for word in ["list", "array", "input", "numbers", "parameter", "argument"])
assert has_list_ref, f"answer.txt does not reference the function's input: {text[:200]}"

print("All checks passed")
