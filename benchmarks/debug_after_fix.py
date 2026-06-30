"""调试修复后的 adapter。"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.core.model import MimoClient, ModelConfig
from agent.core.adapters.mimo_adapter import MimoAdapter

api_key = os.environ.get("MIMO_API_KEY", "tp-cg1y09wjxa62sndexryylklwo70zu5hivav7u9rxn99lnzsn")
config = ModelConfig(
    api_key=api_key,
    base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
    model="mimo-v2.5-pro",
)
client = MimoClient(config)
adapter = MimoAdapter()

messages = [
    {"role": "user", "content": 'Read the file README.md. Use the file_read tool.'}
]
system = "You are a coding agent. Use tools to complete tasks."

result = client.chat_stream(messages, system=system)
text_chunks = list(result.text)
full_text = "".join(text_chunks)

print("=== Full text ===")
print(full_text[:500])

print("\n=== Content blocks ===")
for block in result.content_blocks:
    print(f"type={block.get('type')}, text={str(block.get('text',''))[:100]}")

print("\n=== Parsed ===")
parsed = adapter.parse_response(result.content_blocks)
print(f"text: {repr(parsed.text[:200])}")
print(f"tool_calls: {parsed.tool_calls}")
