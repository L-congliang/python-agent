"""任务执行器 - 执行 Benchmark 任务并验证结果。"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Union
from pathlib import Path

from agent.evaluation.fake_client import FakeModelClient
from agent.core.loop import AgentLoop, LoopConfig
from agent.core.model_adapter import ParsedResponse, ToolCall
from agent.tools.registry import ToolRegistry


class _FakeAdapter:
    """评测用的简化适配器，只返回文本（不解析工具调用）。"""

    def parse_response(self, blocks: list[dict[str, Any]]) -> ParsedResponse:
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return ParsedResponse(text=text, tool_calls=[])

    def supports_native_tools(self) -> bool:
        return False


@dataclass
class StepRecord:
    """单步操作记录。"""

    step_number: int
    action: str  # "model_call" | "tool_call" | "final_answer"
    input_summary: str = ""
    output_summary: str = ""
    duration_ms: int = 0


@dataclass
class EvalResult:
    """单个任务的评测结果。"""

    task_id: str
    passed: bool
    attempts: int
    tool_steps: int
    category: str
    stop_reason: str = ""
    error: str = ""
    steps: list[StepRecord] = field(default_factory=list)


class Evaluator:
    """Benchmark 任务执行器。

    支持两种模式：
    - FakeModelClient：确定性测试，测框架逻辑
    - 真实 API（MimoClient）：端到端测试，测真实能力

    使用方式:
        evaluator = Evaluator()
        result = evaluator.run_task(task, client, fixture_dir="benchmarks/fixtures/bench_readme")
    """

    def __init__(self, max_tool_calls: int = 10) -> None:
        self.max_tool_calls = max_tool_calls

    def _build_registry(self, task: Any) -> ToolRegistry:
        """根据任务的 allowed_tools 创建工具注册表。"""
        registry = ToolRegistry()
        # 注册评测常用的工具
        from agent.tools.bash import bash_tool
        from agent.tools.file_read import file_read_tool
        from agent.tools.file_write import file_write_tool
        from agent.tools.file_edit import file_edit_tool
        from agent.tools.grep import grep_tool
        from agent.tools.glob import glob_tool

        all_tools = {
            "bash": bash_tool,
            "file_read": file_read_tool,
            "file_write": file_write_tool,
            "file_edit": file_edit_tool,
            "grep": grep_tool,
            "glob": glob_tool,
        }

        for tool_name in task.allowed_tools:
            if tool_name in all_tools:
                registry.register(all_tools[tool_name])

        return registry

    def run_task(
        self,
        task: Any,
        client: Union[FakeModelClient, Any],
        fixture_dir: str | Path | None = None,
    ) -> EvalResult:
        """执行单个 Benchmark 任务。

        Args:
            task: BenchmarkTask 对象
            client: FakeModelClient 或 MimoClient
            fixture_dir: fixture 目录路径（会复制到临时目录）

        Returns:
            EvalResult 包含执行结果
        """
        steps: list[StepRecord] = []
        tool_steps = 0
        attempts = 0

        # 1. 准备临时工作目录
        with tempfile.TemporaryDirectory(prefix="bench_") as tmpdir:
            workspace = Path(tmpdir)

            # 复制 fixture 文件
            if fixture_dir is not None:
                src = Path(fixture_dir)
                if src.exists():
                    for item in src.iterdir():
                        dst = workspace / item.name
                        if item.is_dir():
                            shutil.copytree(item, dst)
                        else:
                            shutil.copy2(item, dst)

            # 2. 创建 AgentLoop
            registry = self._build_registry(task)
            config = LoopConfig(
                max_turns=task.step_budget,
                max_tool_calls=task.step_budget,
                system_prompt="You are a coding agent working in a local repository. "
                "You have access to tools that can read, write, and edit files, "
                "as well as run shell commands.\n\n"
                "IMPORTANT: When you need to use a tool, you MUST output the tool call "
                "in the following XML format:\n"
                "<tool_call>\n"
                "<tool_name>TOOL_NAME</tool_name>\n"
                "<arguments>\n"
                "<PARAM_NAME>PARAM_VALUE</PARAM_NAME>\n"
                "</arguments>\n"
                "</tool_call>\n\n"
                "For example, to read a file:\n"
                "<tool_call>\n"
                "<tool_name>file_read</tool_name>\n"
                "<arguments>\n"
                "<file_path>path/to/file.py</file_path>\n"
                "</arguments>\n"
                "</tool_call>\n\n"
                "After receiving tool results, continue working on the task. "
                "When you have completed the task, provide your final answer as plain text.",
            )

            # 根据客户端类型选择适配器
            is_fake = isinstance(client, FakeModelClient)
            adapter = _FakeAdapter() if is_fake else self._create_real_adapter()

            loop = AgentLoop(client, registry, config=config, adapter=adapter)  # type: ignore[arg-type]

            # 3. 执行 AgentLoop
            final_answer = ""
            stop_reason = "max_steps_reached"
            try:
                final_answer = loop.run(task.prompt)
                stop_reason = "final_answer_returned"
                attempts = loop._turn_count
                tool_steps = loop._tool_call_count
                steps.append(StepRecord(
                    step_number=attempts,
                    action="final_answer",
                    output_summary=final_answer[:200],
                ))
            except Exception as e:
                stop_reason = f"error: {type(e).__name__}"
                steps.append(StepRecord(
                    step_number=attempts,
                    action="error",
                    output_summary=str(e)[:200],
                ))

            # 4. 验证结果
            passed = False
            error = ""
            if task.verifier:
                try:
                    verifier_code = self._clean_verifier(task.verifier)
                    result = subprocess.run(
                        [sys.executable, "-c", verifier_code],
                        cwd=str(workspace),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=10,
                    )
                    passed = result.returncode == 0
                    if not passed:
                        error = result.stderr.strip()[:500]
                except subprocess.TimeoutExpired:
                    error = "Verifier timed out after 10s"
                except Exception as e:
                    error = f"Verifier error: {e}"

        return EvalResult(
            task_id=task.id,
            passed=passed,
            attempts=attempts,
            tool_steps=tool_steps,
            category=task.category,
            stop_reason=stop_reason,
            error=error,
            steps=steps,
        )

    def _create_real_adapter(self) -> Any:
        """创建真实的 MimoAdapter。"""
        from agent.core.adapters.mimo_adapter import MimoAdapter
        return MimoAdapter()

    @staticmethod
    def _clean_verifier(verifier: str) -> str:
        """清理 verifier 字符串，兼容 Windows。"""
        code = verifier
        if code.startswith("python3 -c "):
            code = code[len("python3 -c "):]
        if code.startswith('"') and code.endswith('"'):
            code = code[1:-1]
        if code.startswith("'") and code.endswith("'"):
            code = code[1:-1]
        return code
