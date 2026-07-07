"""Observation 端到端 Integration 测试

验证 "真实工具执行 -> ToolResult.observation -> loop 注入 -> 事件回调" 的完整链路。
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

import pytest

from agent.core.context import ToolUseContext, AbortController, FileReadState
from agent.core.loop import AgentLoop, LoopConfig
from agent.core.types import (
    ToolCall, ToolResult, StreamEvent, ObservationMetadata,
    PermissionConfirmationOutcome, PermissionRequest,
)
from agent.tools.registry import ToolRegistry, register_base_tools


# ============================================================
# 辅助函数
# ============================================================


def _always_approve_handler(request: PermissionRequest) -> PermissionConfirmationOutcome:
    """总是批准的权限处理器"""
    return PermissionConfirmationOutcome.APPROVED


def create_test_loop(
    artifact_dir: str | None = None,
    on_tool_result: callable = None,
) -> tuple[AgentLoop, list[tuple[ToolCall, ToolResult]]]:
    """创建测试用的 AgentLoop，返回 (loop, tool_result_log)"""
    mock_client = MagicMock()
    tool_result_log: list[tuple[ToolCall, ToolResult]] = []

    def _on_tool_result(tool_call: ToolCall, result: ToolResult) -> None:
        tool_result_log.append((tool_call, result))

    config = LoopConfig(
        model="test",
        artifact_dir=artifact_dir,
        on_tool_result=on_tool_result or _on_tool_result,
    )
    config.permission_handler = _always_approve_handler
    registry = register_base_tools(ToolRegistry())
    loop = AgentLoop(mock_client, registry, config=config)

    return loop, tool_result_log


# ============================================================
# 端到端测试
# ============================================================


class TestObservationE2E:
    """端到端 Observation 测试。"""

    def test_tool_result_callback_with_observation(self) -> None:
        """工具执行后，on_tool_result 回调收到包含 observation 的 ToolResult"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, log = create_test_loop(artifact_dir=tmpdir)

            # 创建一个会返回长输出的工具调用
            # 注意：这里我们直接测试 _execute_tool_calls，不走完整 loop
            context = ToolUseContext(
                model="test",
                artifact_dir=tmpdir,
            )

            # 执行一个真实的 bash 命令
            tool_call = ToolCall(
                id="test_id",
                name="bash",
                arguments={"command": "echo 'hello world'"},
            )

            results = loop._execute_tool_calls([tool_call])

            # 验证结果
            assert len(results) == 1
            result = results[0]
            assert result.is_error is False
            assert "hello world" in result.output

            # 验证 observation 存在
            assert result.observation is not None
            assert result.observation.was_truncated is False  # 短输出不截断

            # 验证回调被调用
            assert len(log) == 1
            logged_tool_call, logged_result = log[0]
            assert logged_tool_call.name == "bash"
            assert logged_result.observation is not None

    def test_long_bash_output_with_artifact(self) -> None:
        """长 bash 输出应该生成 artifact"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, log = create_test_loop(artifact_dir=tmpdir)

            context = ToolUseContext(
                model="test",
                artifact_dir=tmpdir,
            )

            # 执行一个会生成长输出的命令
            tool_call = ToolCall(
                id="test_id",
                name="bash",
                arguments={"command": "for i in $(seq 1 3000); do echo line $i; done"},
            )

            results = loop._execute_tool_calls([tool_call])

            # 验证结果
            assert len(results) == 1
            result = results[0]
            assert result.is_error is False

            # 验证 observation 存在且被截断
            assert result.observation is not None
            assert result.observation.was_truncated is True
            assert result.observation.artifact_path is not None
            assert os.path.exists(result.observation.artifact_path)

            # 验证 artifact 内容完整
            with open(result.observation.artifact_path, encoding="utf-8") as f:
                artifact_content = f.read()
            assert "line 3000" in artifact_content

            # 验证 preview 是截断版本
            assert "truncated" in result.observation.preview.lower() or \
                   len(result.observation.preview) < len(result.output)

    def test_ask_permission_preserves_observation(self) -> None:
        """ASK 权限确认后，observation 被保留"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一个会返回长输出的工具调用
            # 使用 bash 命令生成长输出
            loop, log = create_test_loop(artifact_dir=tmpdir)

            context = ToolUseContext(
                model="test",
                artifact_dir=tmpdir,
            )

            # 直接测试 _execute_tool_calls，模拟 ASK 权限后的结果包装
            # 先执行一个真实的 bash 命令
            tool_call = ToolCall(
                id="test_id",
                name="bash",
                arguments={"command": "for i in $(seq 1 3000); do echo line $i; done"},
            )

            results = loop._execute_tool_calls([tool_call])
            result = results[0]

            # 模拟 ASK 权限确认后的包装
            confirmation_note = "[已确认执行] 用户已确认执行工具 'bash'。"
            wrapped_result = ToolResult(
                output=f"{confirmation_note}\n{result.output}",
                is_error=result.is_error,
                new_messages=result.new_messages,
                observation=result.observation,  # 保留 observation
            )

            # 验证 observation 被保留
            assert wrapped_result.observation is not None
            assert wrapped_result.observation.was_truncated is True
            assert wrapped_result.observation.artifact_path is not None

    def test_handle_tool_results_uses_observation_preview(self) -> None:
        """_handle_tool_results 使用 observation.preview 而不是 output"""
        loop, log = create_test_loop()

        # 创建一个带 observation 的 ToolResult
        tool_call = ToolCall(id="test_id", name="bash", arguments={})
        result = ToolResult(
            output="full output here",
            observation=ObservationMetadata(
                preview="preview text",
                was_truncated=True,
                full_output_chars=100,
            ),
        )

        # 调用 _handle_tool_results
        loop._handle_tool_results([tool_call], [result])

        # 验证消息历史中使用的是 preview
        assert len(loop._messages) == 1
        msg = loop._messages[0]
        assert msg["role"] == "user"
        assert len(msg["content"]) == 1
        assert msg["content"][0]["content"] == "preview text"

    def test_handle_tool_results_fallback_to_output(self) -> None:
        """没有 observation 时，_handle_tool_results 使用 output"""
        loop, log = create_test_loop()

        tool_call = ToolCall(id="test_id", name="bash", arguments={})
        result = ToolResult(output="fallback output")

        loop._handle_tool_results([tool_call], [result])

        assert len(loop._messages) == 1
        msg = loop._messages[0]
        assert msg["content"][0]["content"] == "fallback output"


# ============================================================
# 边界测试
# ============================================================


class TestObservationE2EEdgeCases:
    """端到端边界情况测试。"""

    def test_no_artifact_dir(self) -> None:
        """artifact_dir 为 None 时，不保存 artifact"""
        loop, log = create_test_loop(artifact_dir=None)

        context = ToolUseContext(model="test", artifact_dir=None)

        tool_call = ToolCall(
            id="test_id",
            name="bash",
            arguments={"command": "for i in $(seq 1 3000); do echo line $i; done"},
        )

        results = loop._execute_tool_calls([tool_call])
        result = results[0]

        # 验证 observation 存在但没有 artifact
        assert result.observation is not None
        assert result.observation.was_truncated is True
        assert result.observation.artifact_path is None

    def test_unicode_output(self) -> None:
        """Unicode 内容正常处理"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loop, log = create_test_loop(artifact_dir=tmpdir)

            context = ToolUseContext(model="test", artifact_dir=tmpdir)

            tool_call = ToolCall(
                id="test_id",
                name="bash",
                arguments={"command": "echo '中文测试'"},
            )

            results = loop._execute_tool_calls([tool_call])
            result = results[0]

            assert "中文测试" in result.output
            assert result.observation is not None
