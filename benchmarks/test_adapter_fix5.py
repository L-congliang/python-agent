"""检查实际字符。"""

text1 = '<tool_call>\n<tool_name>bash</tool_name>\n<arguments>\n<command>ls</command>\n</arguments>\n</tool_call>'

# 检查前几个字符
print("First 20 chars:")
for i, ch in enumerate(text1[:20]):
    print(f"  {i}: {repr(ch)} (ord={ord(ch)})")

print()

# 检查 <tool> 部分
print("Looking for '<tool>':")
for i in range(len(text1) - 5):
    if text1[i:i+5] == '<tool':
        print(f"  Found at {i}: {repr(text1[i:i+10])}")

print()

# 检查 </tool> 部分
print("Looking for '</tool>':")
for i in range(len(text1) - 6):
    if text1[i:i+6] == '</tool':
        print(f"  Found at {i}: {repr(text1[i:i+10])}")
