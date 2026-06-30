"""调试 adapter 正则 - 最终版。"""

import re

text1 = '<tool_call>\n<tool_name>bash</tool_name>\n<arguments>\n<command>ls</command>\n</arguments>\n</tool_call>'

pattern = r"<tool>(.*?)</tool>"

# 手动测试
print("Text:", repr(text1))
print()

# 找所有匹配
for m in re.finditer(pattern, text1, re.DOTALL):
    print(f"Match at {m.start()}-{m.end()}: {repr(m.group()[:50])}")

# 也用 findall
matches = re.findall(pattern, text1, re.DOTALL)
print(f"\nfindall: {len(matches)} matches")
for m in matches:
    print(f"  {repr(m[:50])}")
