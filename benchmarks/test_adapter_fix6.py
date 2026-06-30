"""调试 Test 2。"""

import re

text2 = '<tool_call>\n<tool>{"name": "file_read", "args": {"path": "README.md"}}</tool>\n</tool_call>'

print("Text:", repr(text2))
print()

# 测试 pattern2
pattern2 = r"<tool>(.*?)</tool>"
matches = re.findall(pattern2, text2, re.DOTALL)
print(f"Pattern2 matches: {len(matches)}")
for m in matches:
    print(f"  {repr(m[:80])}")
