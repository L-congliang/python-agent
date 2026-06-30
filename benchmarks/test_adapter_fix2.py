"""调试 adapter 正则。"""

import re

# 测试 1：旧格式
text1 = '<tool_call>\n<tool_name>bash</tool_name>\n<arguments>\n<command>ls</command>\n</arguments>\n</tool_call>'
pattern = r"\<tool\>(.*?)\<\/tool\>"
matches = re.findall(pattern, text1, re.DOTALL)
print(f"Test 1 matches: {len(matches)}")
for m in matches:
    print(f"  content: {repr(m[:50])}")

# 测试 2：新格式
text2 = '<tool_call>\n<tool>{"name": "file_read", "args": {"path": "README.md"}}</tool>\n</tool_call>'
matches2 = re.findall(pattern, text2, re.DOTALL)
print(f"\nTest 2 matches: {len(matches2)}")
for m in matches2:
    print(f"  content: {repr(m[:50])}")
