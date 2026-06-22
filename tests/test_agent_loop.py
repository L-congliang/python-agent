"""
测试 Agent 主循环（loop.py）

覆盖场景:
1. 纯文本对话
2. 单次工具调用
3. 多次工具调用
4. 工具执行失败
5. 最大轮次超限
6. 中断支持
7. 消息历史累积
8. reset 清空历史
9. Token 追踪
10. 自动压缩
"""

import threading
import time
from unittest.mock import MagicMock

import pytest

from agent.core.loop import AgentLoop, LoopConfig
from agent.core.model import MimoClient, StreamResult
from agent.core.types import ToolResult
from agent.tools.base import build_tool
from agent.tools.registry import ToolRegistry


# ============================================================
# 测试辅助：Mock 工具
# ============================================================


def _make_read_tool():
    """创建一个模拟的文件读取工具"""
    def execute(input, context):
        path = input.get("path", "")
        if path == "missing.txt":
            return ToolResult(output="文件不存在: missing.txt", is_error=True)
        return ToolResult(output=f"内容: {path}")

    return build_tool(
        name="read",
        description="读取文件",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        execute_fn=execute,
    )


def _make_noop_tool():
    """创建一个什么都不做的工具"""
    def execute(input, context):
        return ToolResult(output="ok")

    return build_tool(
        name="noop",
        description="空操作",
        parameters={"type": "object", "properties": {}},
        execute_fn=execute,
    )


# ============================================================
# 测试辅助：Mock MimoClient
# ============================================================


def _mock_client(responses):
    """创建 mock MimoClient，按顺序返回预设响应

    Args:
        responses: StreamResult 列表，每次 chat_stream() 调用返回一个
    """
    client = MagicMock(spec=MimoClient)
    iter_responses = iter(responses)
    client.chat_stream = MagicMock(side_effect=lambda *a, **kw: next(iter_responses))
    return client


def _text_stream(chunks, content_blocks):
    """创建纯文本的 StreamResult

    Args:
        chunks: 文本 chunk 列表
        content_blocks: 最终 content blocks
    """
    return StreamResult(text=iter(chunks), content_blocks=content_blocks)


def _tool_stream(text, tool_calls_data, tool_results_content=None):
    """创建包含 tool_use 的 StreamResult

    Args:
        text: 文本内容
        tool_calls_data: tool_use block 列表 [{"id": ..., "name": ..., "input": ...}]
        tool_results_content: 可选，工具结果（用于测试）
    """
    content_blocks = [{"type": "text", "text": text}]
    for tc in tool_calls_data:
        content_blocks.append({
            "type": "tool_use",
            "id": tc["id"],
            "name": tc["name"],
            "input": tc.get("input", {}),
        })
    return StreamResult(text=iter([text]), content_blocks=content_blocks)


# ============================================================
# 测试类
# ============================================================


class TestAgentLoopSimpleText:
    """纯文本对话测试"""

    def test_simple_text_response(self):
        """模型返回纯文本，不调用工具"""
        client = _mock_client([
            _text_stream(["你好！"], [{"type": "text", "text": "你好！"}]),
        ])
        registry = ToolRegistry()
        loop = AgentLoop(client, registry)

        reply = loop.run("你好")
        assert reply == "你好！"
        assert loop.turn_count == 1
        assert loop.tool_call_count == 0

    def test_simple_stream_response(self):
        """流式返回纯文本"""
        client = _mock_client([
            _text_stream(["你", "好", "！"], [{"type": "text", "text": "你好！"}]),
        ])
        registry = ToolRegistry()
        loop = AgentLoop(client, registry)

        chunks = list(loop.run_stream("你好"))
        assert chunks == ["你", "好", "！"]
        assert loop.turn_count == 1
        assert loop.tool_call_count == 0


class TestAgentLoopToolCall:
    """工具调用测试"""

    def test_single_tool_call(self):
        """模型调用一次工具，然后返回结果"""
        client = _mock_client([
            # 第一次回复：调用工具
            _tool_stream("我来读取文件", [
                {"id": "t1", "name": "read", "input": {"path": "test.txt"}},
            ]),
            # 第二次回复：基于工具结果回复
            _text_stream(["文件内容是 内容: test.txt"], [
                {"type": "text", "text": "文件内容是 内容: test.txt"},
            ]),
        ])
        registry = ToolRegistry()
        registry.register(_make_read_tool())
        loop = AgentLoop(client, registry)

        reply = loop.run("读取 test.txt")
        assert "内容: test.txt" in reply
        assert loop.tool_call_count == 1

    def test_single_tool_call_stream(self):
        """流式模式下单次工具调用"""
        client = _mock_client([
            _tool_stream("我来读取文件", [
                {"id": "t1", "name": "read", "input": {"path": "test.txt"}},
            ]),
            _text_stream(["文件内容是 内容: test.txt"], [
                {"type": "text", "text": "文件内容是 内容: test.txt"},
            ]),
        ])
        registry = ToolRegistry()
        registry.register(_make_read_tool())
        loop = AgentLoop(client, registry)

        chunks = list(loop.run_stream("读取 test.txt"))
        full = "".join(chunks)
        assert "内容: test.txt" in full
        assert loop.tool_call_count == 1

    def test_multiple_tool_calls(self):
        """模型在一个 turn 中调用多个工具"""
        client = _mock_client([
            _tool_stream("", [
                {"id": "t1", "name": "read", "input": {"path": "a.txt"}},
                {"id": "t2", "name": "read", "input": {"path": "b.txt"}},
            ]),
            _text_stream(["两个文件都读完了"], [
                {"type": "text", "text": "两个文件都读完了"},
            ]),
        ])
        registry = ToolRegistry()
        registry.register(_make_read_tool())
        loop = AgentLoop(client, registry)

        reply = loop.run("读取 a.txt 和 b.txt")
        assert loop.tool_call_count == 2
        assert "两个文件都读完了" in reply

    def test_tool_execution_error(self):
        """工具执行失败时，错误信息返回给模型"""
        client = _mock_client([
            _tool_stream("", [
                {"id": "t1", "name": "read", "input": {"path": "missing.txt"}},
            ]),
            _text_stream(["文件不存在"], [
                {"type": "text", "text": "文件不存在"},
            ]),
        ])
        registry = ToolRegistry()
        registry.register(_make_read_tool())
        loop = AgentLoop(client, registry)

        reply = loop.run("读取 missing.txt")
        assert "不存在" in reply

    def test_unknown_tool(self):
        """模型调用不存在的工具"""
        client = _mock_client([
            _tool_stream("", [
                {"id": "t1", "name": "unknown_tool", "input": {}},
            ]),
            _text_stream(["工具不存在"], [
                {"type": "text", "text": "工具不存在"},
            ]),
        ])
        registry = ToolRegistry()
        loop = AgentLoop(client, registry)

        reply = loop.run("调用未知工具")
        # 工具不存在时会返回错误，模型会看到错误信息
        assert loop.tool_call_count == 1


class TestAgentLoopLimits:
    """限制测试"""

    def test_max_turns_exceeded(self):
        """超过最大轮次时停止"""
        # 模型每次都调用工具，永不停止
        responses = []
        for i in range(10):
            responses.append(_tool_stream("", [
                {"id": f"t{i}", "name": "noop", "input": {}},
            ]))
        client = _mock_client(responses)

        registry = ToolRegistry()
        registry.register(_make_noop_tool())
        loop = AgentLoop(client, registry, LoopConfig(max_turns=3))

        reply = loop.run("无限循环测试")
        assert "轮次" in reply
        assert loop.turn_count <= 3

    def test_max_tool_calls_exceeded(self):
        """超过最大工具调用次数时停止"""
        client = _mock_client([
            _tool_stream("", [
                {"id": "t1", "name": "noop", "input": {}},
                {"id": "t2", "name": "noop", "input": {}},
            ]),
        ])
        registry = ToolRegistry()
        registry.register(_make_noop_tool())
        loop = AgentLoop(client, registry, LoopConfig(max_tool_calls=1))

        reply = loop.run("工具调用超限")
        assert "工具调用次数" in reply


class TestAgentLoopAbort:
    """中断测试"""

    def test_abort(self):
        """可以中断正在执行的循环"""
        # 创建一个慢工具
        def slow_execute(input, context):
            time.sleep(10)
            return ToolResult(output="done")

        slow_tool = build_tool(
            name="slow",
            description="慢操作",
            parameters={"type": "object", "properties": {}},
            execute_fn=slow_execute,
        )

        client = _mock_client([
            _tool_stream("", [{"id": "t1", "name": "slow", "input": {}}]),
            _text_stream(["完成"], [{"type": "text", "text": "完成"}]),
        ])
        registry = ToolRegistry()
        registry.register(slow_tool)
        loop = AgentLoop(client, registry)

        def abort_after_delay():
            time.sleep(0.2)
            loop.abort()

        threading.Thread(target=abort_after_delay).start()

        with pytest.raises(KeyboardInterrupt):
            loop.run("慢操作")


class TestAgentLoopHistory:
    """消息历史测试"""

    def test_message_history(self):
        """多轮对话保持消息历史"""
        client = _mock_client([
            _text_stream(["好的"], [{"type": "text", "text": "好的"}]),
            _text_stream(["你让我记住 42"], [{"type": "text", "text": "你让我记住 42"}]),
        ])
        registry = ToolRegistry()
        loop = AgentLoop(client, registry)

        loop.run("记住数字 42")
        loop.run("我让你记住什么？")

        # 验证消息历史包含之前的对话
        assert len(loop.messages) >= 4  # 2轮 × (user + assistant)

    def test_reset(self):
        """reset 清空消息历史"""
        client = _mock_client([
            _text_stream(["好的"], [{"type": "text", "text": "好的"}]),
        ])
        registry = ToolRegistry()
        loop = AgentLoop(client, registry)

        loop.run("测试")
        assert len(loop.messages) > 0

        loop.reset()
        assert len(loop.messages) == 0
        assert loop.turn_count == 0
        assert loop.tool_call_count == 0

    def test_messages_returns_copy(self):
        """messages 属性返回副本，不影响内部状态"""
        client = _mock_client([
            _text_stream(["好的"], [{"type": "text", "text": "好的"}]),
        ])
        registry = ToolRegistry()
        loop = AgentLoop(client, registry)

        loop.run("测试")
        msgs = loop.messages
        msgs.clear()  # 清空副本
        assert len(loop.messages) > 0  # 内部状态不受影响


class TestAgentLoopConfig:
    """配置测试"""

    def test_default_config(self):
        """默认配置的值"""
        config = LoopConfig()
        assert config.model == "mimo-v2.5-pro"
        assert config.max_tokens == 4096
        assert config.max_turns == 50
        assert config.max_tool_calls == 100

    def test_custom_config(self):
        """自定义配置"""
        config = LoopConfig(max_turns=5, max_tool_calls=10, debug=True)
        assert config.max_turns == 5
        assert config.max_tool_calls == 10
        assert config.debug is True

    def test_system_prompt(self):
        """系统提示被正确传递"""
        client = _mock_client([
            _text_stream(["好的"], [{"type": "text", "text": "好的"}]),
        ])
        registry = ToolRegistry()
        config = LoopConfig(system_prompt="你是一个测试助手")
        loop = AgentLoop(client, registry, config)

        loop.run("你好")

        # 验证 chat_stream 被调用时传入了 system prompt
        call_kwargs = client.chat_stream.call_args
        assert "你是一个测试助手" in call_kwargs.kwargs.get("system", call_kwargs[1].get("system", ""))


class TestAgentLoopToolResultFormat:
    """工具结果格式测试"""

    def test_tool_result_injected_correctly(self):
        """工具结果正确注入消息历史"""
        client = _mock_client([
            _tool_stream("", [
                {"id": "t1", "name": "read", "input": {"path": "test.txt"}},
            ]),
            _text_stream(["ok"], [{"type": "text", "text": "ok"}]),
        ])
        registry = ToolRegistry()
        registry.register(_make_read_tool())
        loop = AgentLoop(client, registry)

        loop.run("读取 test.txt")

        # 检查消息历史中是否有 tool_result
        msgs = loop.messages
        tool_result_msgs = [m for m in msgs if m.get("role") == "user" and isinstance(m.get("content"), list)]
        assert len(tool_result_msgs) >= 1

        # 检查 tool_result 格式
        tool_result_content = tool_result_msgs[0]["content"]
        assert any(block.get("type") == "tool_result" for block in tool_result_content)

    def test_error_tool_result_has_is_error(self):
        """错误的工具结果包含 is_error 标记"""
        client = _mock_client([
            _tool_stream("", [
                {"id": "t1", "name": "read", "input": {"path": "missing.txt"}},
            ]),
            _text_stream(["文件不存在"], [{"type": "text", "text": "文件不存在"}]),
        ])
        registry = ToolRegistry()
        registry.register(_make_read_tool())
        loop = AgentLoop(client, registry)

        loop.run("读取 missing.txt")

        # 找到 tool_result 消息
        msgs = loop.messages
        tool_result_msgs = [m for m in msgs if m.get("role") == "user" and isinstance(m.get("content"), list)]

        # 检查 is_error 标记
        found_error = False
        for msg in tool_result_msgs:
            for block in msg["content"]:
                if block.get("type") == "tool_result" and block.get("is_error"):
                    found_error = True
                    break
        assert found_error


class TestAgentLoopTokenTracking:
    """Token 追踪测试"""

    def test_token_count_starts_at_zero(self):
        """初始 token 计数为 0"""
        client = _mock_client([
            _text_stream(["你好"], [{"type": "text", "text": "你好"}]),
        ])
        registry = ToolRegistry()
        loop = AgentLoop(client, registry)

        assert loop.token_count == 0

    def test_token_count_accumulates(self):
        """多轮对话后 token 计数正确累加"""
        # 创建带 usage 的 StreamResult
        def _text_stream_with_usage(chunks, content_blocks, usage):
            result = StreamResult(text=iter(chunks), content_blocks=content_blocks)
            result.usage = usage
            return result

        client = _mock_client([
            _text_stream_with_usage(["你好"], [{"type": "text", "text": "你好"}], {"input_tokens": 100, "output_tokens": 50}),
            _text_stream_with_usage(["好的"], [{"type": "text", "text": "好的"}], {"input_tokens": 120, "output_tokens": 60}),
        ])
        registry = ToolRegistry()
        loop = AgentLoop(client, registry)

        loop.run("你好")
        assert loop.token_count == 100  # 只累加 input_tokens

        loop.run("继续")
        assert loop.token_count == 220  # 100 + 120

    def test_token_count_resets(self):
        """reset 后 token 计数清零"""
        def _text_stream_with_usage(chunks, content_blocks, usage):
            result = StreamResult(text=iter(chunks), content_blocks=content_blocks)
            result.usage = usage
            return result

        client = _mock_client([
            _text_stream_with_usage(["你好"], [{"type": "text", "text": "你好"}], {"input_tokens": 100, "output_tokens": 50}),
        ])
        registry = ToolRegistry()
        loop = AgentLoop(client, registry)

        loop.run("你好")
        assert loop.token_count == 100

        loop.reset()
        assert loop.token_count == 0

    def test_compact_resets_token_count(self):
        """手动压缩后 token 计数重置"""
        def _text_stream_with_usage(chunks, content_blocks, usage):
            result = StreamResult(text=iter(chunks), content_blocks=content_blocks)
            result.usage = usage
            return result

        client = _mock_client([
            _text_stream_with_usage(["你好"], [{"type": "text", "text": "你好"}], {"input_tokens": 100, "output_tokens": 50}),
        ])
        # Mock compressor
        client.chat = MagicMock(return_value="摘要内容")

        registry = ToolRegistry()
        loop = AgentLoop(client, registry)

        loop.run("你好")
        assert loop.token_count == 100

        loop.compact()
        assert loop.token_count == 0

    def test_auto_compaction_triggered(self):
        """token 达到阈值时自动触发压缩"""
        def _text_stream_with_usage(chunks, content_blocks, usage):
            result = StreamResult(text=iter(chunks), content_blocks=content_blocks)
            result.usage = usage
            return result

        # 设置 context_window=1000，阈值为 800
        client = _mock_client([
            _text_stream_with_usage(["你好"], [{"type": "text", "text": "你好"}], {"input_tokens": 900, "output_tokens": 50}),
        ])
        # Mock compressor
        client.chat = MagicMock(return_value="摘要内容")

        registry = ToolRegistry()
        config = LoopConfig(context_window=1000)
        loop = AgentLoop(client, registry, config)

        loop.run("你好")
        # 900 >= 800 (1000 * 0.8)，应该触发压缩
        assert loop.token_count == 0  # 压缩后重置
