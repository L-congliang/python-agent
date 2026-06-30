"""调试 adapter 正则 - 看实际字符。"""

import re

text1 = '<tool_call>\n<tool_name>bash</tool_name>\n<arguments>\n<command>ls</command>\n</arguments>\n</tool_call>'

print("Text repr:")
print(repr(text1))
print()

# 找所有 <tool 相关的位置
for i, ch in enumerate(text1):
    if text1[i:i+5] == '<tool':
        print(f"Found '<tool' at position {i}: {repr(text1[i:i+20])}")
    if text1[i:i+6] == '</tool':
        print(f"Found '</tool' at position {i}: {repr(text1[i:i+20])}")

print()

# 测试正则
pattern = r"\<tool\>(.*?)\<\/tool\>"
matches = re.findall(pattern, text1, re.DOTALL)
print(f"Pattern matches: {len(matches)}")

# 也试试不转义的正则
pattern2 = r"<tool>(.*?)</tool>"
matches2 = re.findall(pattern2, text1, re.DOTALL)
print(f"Pattern2 matches: {len(matches2)}")
