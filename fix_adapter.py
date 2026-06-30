import pathlib
fp = pathlib.Path("src/agent/core/adapters/mimo_adapter.py")
t = fp.read_text(encoding="utf-8")
print("Lines:", len(t.splitlines()))
old1 = "                    tool_calls.append(ToolCall(name=tool_name, arguments=arguments))\n\n            except Exception"
new1 = "                    tool_calls.append(ToolCall(name=tool_name, arguments=arguments))\n                    continue\n\n                func_match = re.search(r\"<function_(\\w+)\">\", content)\n                if func_match:\n                    arguments = self._parse_anthropic_params(content)\n                    tool_calls.append(ToolCall(name=func_match.group(1), arguments=arguments))\n\n            except Exception"
if old1 in t:
    t = t.replace(old1, new1)
    print("Fix1 done")
else:
    print("Fix1 skip")
