"""真实任务级 e2e regression 测试。"""

from __future__ import annotations

from pathlib import Path

from agent.core.loop import AgentLoop, LoopConfig
from agent.core.model import StreamResult
from agent.core.types import PermissionConfirmationOutcome
from agent.tools.bash import bash_tool
from agent.tools.file_edit import file_edit_tool
from agent.tools.file_read import file_read_tool
from agent.tools.file_write import file_write_tool
from agent.tools.glob import glob_tool
from agent.tools.registry import ToolRegistry


def _text_stream(text: str) -> StreamResult:
    return StreamResult(
        text=iter([text]),
        content_blocks=[{"type": "text", "text": text}],
    )


def _tool_stream(text: str, tool_calls: list[dict]) -> StreamResult:
    blocks = [{"type": "text", "text": text}]
    for tool_call in tool_calls:
        blocks.append(
            {
                "type": "tool_use",
                "id": tool_call["id"],
                "name": tool_call["name"],
                "input": tool_call.get("input", {}),
            }
        )
    return StreamResult(text=iter([text]), content_blocks=blocks)


class FakeClient:
    """按顺序返回预设响应的假模型。"""

    def __init__(self, responses: list[StreamResult]) -> None:
        self._responses = iter(responses)

    def chat_stream(self, messages, system="", tools=None):
        return next(self._responses)


def _make_loop(
    tmp_path: Path,
    responses: list[StreamResult],
    registry: ToolRegistry,
) -> AgentLoop:
    return AgentLoop(
        FakeClient(responses),  # type: ignore[arg-type]
        registry,
        config=LoopConfig(
            workspace_root=str(tmp_path),
            enable_trace=False,
            enable_checkpoint=False,
            enable_subagent=False,
            memory_enabled=False,
            max_turns=8,
        ),
    )


def _collect_tool_results(loop: AgentLoop) -> str:
    blocks: list[str] = []
    for message in loop.messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_result":
                blocks.append(str(block.get("content", "")))
    return "\n".join(blocks)


def test_e2e_agent_reads_edits_and_runs_tests(tmp_path: Path):
    calculator = tmp_path / "calculator.py"
    calculator.write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    (tmp_path / "test_calculator.py").write_text(
        "from calculator import add\n\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )

    registry = ToolRegistry()
    registry.register(file_read_tool)
    registry.register(file_edit_tool)
    registry.register(bash_tool)

    loop = _make_loop(
        tmp_path,
        [
            _tool_stream(
                "先读文件",
                [{"id": "t1", "name": "read", "input": {"file_path": "calculator.py"}}],
            ),
            _tool_stream(
                "准备修复",
                [
                    {
                        "id": "t2",
                        "name": "edit",
                        "input": {
                            "file_path": "calculator.py",
                            "old_string": "return a - b",
                            "new_string": "return a + b",
                        },
                    }
                ],
            ),
            _tool_stream(
                "运行测试",
                [
                    {
                        "id": "t3",
                        "name": "bash",
                        "input": {
                            "command": "python -m pytest test_calculator.py -q",
                            "workdir": str(tmp_path),
                            "timeout": 30,
                        },
                    }
                ],
            ),
            _text_stream("已修复 calculator.py 中的 bug，并运行测试通过。"),
        ],
        registry,
    )
    loop.set_permission_handler(lambda request: PermissionConfirmationOutcome.APPROVED)

    reply = loop.run("修复 calculator.py 的 bug 并运行测试")

    assert "测试通过" in reply
    assert "return a + b" in calculator.read_text(encoding="utf-8")
    assert loop.tool_call_count == 3


def test_e2e_permission_confirmation_blocks_write_when_rejected_and_allows_when_approved(
    tmp_path: Path,
):
    reject_registry = ToolRegistry()
    reject_registry.register(file_write_tool)
    reject_loop = _make_loop(
        tmp_path,
        [
            _tool_stream(
                "尝试写入",
                [
                    {
                        "id": "t1",
                        "name": "write",
                        "input": {"file_path": "draft.txt", "content": "hello"},
                    }
                ],
            ),
            _text_stream("第一次写入被拒绝。"),
        ],
        reject_registry,
    )
    reject_loop.set_permission_handler(lambda request: PermissionConfirmationOutcome.DENIED)

    reject_reply = reject_loop.run("创建 draft.txt")

    assert "拒绝" in reject_reply
    assert not (tmp_path / "draft.txt").exists()
    assert "用户拒绝" in _collect_tool_results(reject_loop)

    approve_registry = ToolRegistry()
    approve_registry.register(file_write_tool)
    approve_loop = _make_loop(
        tmp_path,
        [
            _tool_stream(
                "再次写入",
                [
                    {
                        "id": "t1",
                        "name": "write",
                        "input": {"file_path": "draft.txt", "content": "hello"},
                    }
                ],
            ),
            _text_stream("第二次写入已完成。"),
        ],
        approve_registry,
    )
    approve_loop.set_permission_handler(lambda request: PermissionConfirmationOutcome.APPROVED)

    approve_reply = approve_loop.run("再次创建 draft.txt")

    assert "已完成" in approve_reply
    assert (tmp_path / "draft.txt").read_text(encoding="utf-8") == "hello"
    assert "已确认执行" in _collect_tool_results(approve_loop)


def test_e2e_workspace_guard_blocks_external_search(tmp_path: Path):
    inside = tmp_path / "inside.txt"
    inside.write_text("safe", encoding="utf-8")

    outside_dir = tmp_path.parent / f"{tmp_path.name}_outside"
    outside_dir.mkdir(exist_ok=True)
    (outside_dir / "secret.txt").write_text("secret", encoding="utf-8")

    registry = ToolRegistry()
    registry.register(glob_tool)

    loop = _make_loop(
        tmp_path,
        [
            _tool_stream(
                "先尝试搜索工作区外文件",
                [
                    {
                        "id": "t1",
                        "name": "glob",
                        "input": {"pattern": "*.txt", "path": f"../{outside_dir.name}"},
                    }
                ],
            ),
            _tool_stream(
                "改为搜索工作区内文件",
                [
                    {
                        "id": "t2",
                        "name": "glob",
                        "input": {"pattern": "*.txt", "path": "."},
                    }
                ],
            ),
            _text_stream("已完成受限搜索。"),
        ],
        registry,
    )

    reply = loop.run("先搜索工作区外，再搜索工作区内")
    tool_results = _collect_tool_results(loop)

    assert "受限搜索" in reply
    assert "escape" in tool_results.lower()
    assert "inside.txt" in tool_results
