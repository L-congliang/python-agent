import pathlib
fp = pathlib.Path("src/agent/core/adapters/mimo_adapter.py")
lines = fp.read_text(encoding="utf-8").split("\n")
for i, line in enumerate(lines[135:], start=136):
    print(f"{i:3d} | {line}")
