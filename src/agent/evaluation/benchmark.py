"""Benchmark 任务定义和加载器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import json
from pathlib import Path


@dataclass
class BenchmarkTask:
    """单个 Benchmark 任务。"""

    id: str
    prompt: str
    fixture_repo: str
    allowed_tools: list[str]
    step_budget: int
    expected_artifact: str
    verifier: str
    category: str
    setup: dict[str, Any] | None = None


REQUIRED_TASK_FIELDS = ("id", "prompt", "allowed_tools", "step_budget", "verifier", "category")


def load_benchmark(path: str | Path) -> list[BenchmarkTask]:
    """从 JSON 文件加载 Benchmark 任务列表。

    Raises:
        ValueError: JSON 格式错误或缺少必需字段。
    """
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text)

    if "tasks" not in data:
        raise ValueError(f"Benchmark file missing 'tasks' key: {path}")

    tasks = []
    for index, item in enumerate(data["tasks"]):
        missing = [f for f in REQUIRED_TASK_FIELDS if f not in item]
        if missing:
            raise ValueError(
                f"Task #{index} missing required fields: {missing}"
            )
        tasks.append(BenchmarkTask(
            id=item["id"],
            prompt=item["prompt"],
            fixture_repo=item.get("fixture_repo", ""),
            allowed_tools=item["allowed_tools"],
            step_budget=item["step_budget"],
            expected_artifact=item.get("expected_artifact", ""),
            verifier=item["verifier"],
            category=item["category"],
            setup=item.get("setup"),
        ))
    return tasks
