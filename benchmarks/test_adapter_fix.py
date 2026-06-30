"""验证 adapter 修复。"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.core.adapters.mimo_adapter import MimoAdapter

adapter = MimoAdapter()

# 测试 1：旧格式
text1 = '<tool_call>\n<tool_name>bash</tool_name>\n<arguments>\n<command>ls</command>\n</arguments>\n</tool_call>'
result1 = adapter._parse_tool_calls(text1)
print(f"Test 1 (old format): {len(result1)} tool calls")
for tc in result1:
    print(f"  name={tc.name}, args={tc.arguments}")

# 测试 2：新格式
text2 = '<tool_call>\n<tool>{"name": "file_read", "args": {"path": "README.md"}}</tool>\n</tool_call>'
result2 = adapter._parse_tool_calls(text2)
print(f"\nTest 2 (new format): {len(result2)} tool calls")
for tc in result2:
    print(f"  name={tc.name}, args={tc.arguments}")

# 测试 3：无工具调用
text3 = "This is just plain text."
result3 = adapter._parse_tool_calls(text3)
print(f"\nTest 3 (no tool call): {len(result3)} tool calls")

print("\nAll tests passed!" if len(result1) == 1 and len(result2) == 1 and len(result3) == 0 else "\nSome tests FAILED!")
