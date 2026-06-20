"""CLI 测试 - AgentApp 的各种场景"""

from unittest.mock import MagicMock, patch
from collections.abc import Iterator

import pytest
from rich.console import Console

from agent.cli.app import AgentApp, BRAND_COLOR
from agent.core.types import StreamEvent


def make_app(on_message=None) -> AgentApp:
    """创建测试用的 AgentApp"""
    if on_message is None:
        def on_message(msg: str) -> Iterator[StreamEvent]:
            return iter([])
    return AgentApp(on_message=on_message)


class TestAgentAppInit:
    """初始化测试"""

    def test_init_default(self):
        app = make_app()
        assert app.console is not None
        assert app._stream_buffer == ""
        assert app.model == "mimo-v2.5-pro"
        assert app.version == "0.1.0"

    def test_init_custom(self):
        app = AgentApp(
            on_message=lambda m: iter([]),
            model="test-model",
            version="1.0.0",
        )
        assert app.model == "test-model"
        assert app.version == "1.0.0"


class TestHeader:
    """Header 测试"""

    def test_show_header(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.show_header()
            mock_print.assert_called_once()
            # 验证是 Panel 对象
            from rich.panel import Panel
            assert isinstance(mock_print.call_args[0][0], Panel)


class TestInput:
    """输入测试"""

    def test_get_input(self):
        app = make_app()
        with patch.object(app.console, "input", return_value="hello"):
            result = app.get_input()
        assert result == "hello"

    def test_get_input_keyboard_interrupt(self):
        app = make_app()
        with patch.object(app.console, "input", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                app.get_input()

    def test_get_input_eof(self):
        app = make_app()
        with patch.object(app.console, "input", side_effect=EOFError):
            with pytest.raises(EOFError):
                app.get_input()


class TestCommands:
    """命令处理测试"""

    def test_exit_command(self):
        app = make_app()
        with pytest.raises(EOFError):
            app._handle_command("/exit")

    def test_quit_command(self):
        app = make_app()
        with pytest.raises(EOFError):
            app._handle_command("/quit")

    def test_help_command(self):
        app = make_app()
        with patch.object(app.console, "print"):
            assert app._handle_command("/help") is True

    def test_clear_command(self):
        app = make_app()
        with patch.object(app.console, "clear"):
            assert app._handle_command("/clear") is True

    def test_reset_command(self):
        app = make_app()
        with patch.object(app.console, "print"):
            assert app._handle_command("/reset") is True

    def test_unknown_command(self):
        app = make_app()
        assert app._handle_command("/unknown") is False

    def test_not_command(self):
        app = make_app()
        assert app._handle_command("hello") is False


class TestStreamBuffering:
    """流式缓冲测试"""

    def test_chunks_buffered_until_newline(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.render_stream_chunk("Hello")
            mock_print.assert_not_called()
            app.render_stream_chunk(" World\n")
            mock_print.assert_called_once()

    def test_multiple_lines_in_one_chunk(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.render_stream_chunk("line1\nline2\nline3")
            assert mock_print.call_count == 2

    def test_flush_renders_remaining(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.render_stream_chunk("partial")
            mock_print.assert_not_called()
            app.flush_stream()
            mock_print.assert_called_once()

    def test_flush_empty_buffer(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.flush_stream()
            mock_print.assert_not_called()

    def test_buffer_reset_after_flush(self):
        app = make_app()
        app.render_stream_chunk("test")
        app.flush_stream()
        assert app._stream_buffer == ""


class TestToolCallPanel:
    """工具调用面板测试"""

    def test_show_tool_call(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.show_tool_call("file_read", {"path": "test.py"})
            mock_print.assert_called_once()
            from rich.panel import Panel
            assert isinstance(mock_print.call_args[0][0], Panel)

    def test_show_tool_call_multiple_args(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.show_tool_call("file_write", {"path": "test.py", "content": "hello"})
            mock_print.assert_called_once()


class TestToolResultPanel:
    """工具结果面板测试"""

    def test_show_tool_result_success(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.show_tool_result("output", is_error=False)
            mock_print.assert_called_once()

    def test_show_tool_result_error(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.show_tool_result("error", is_error=True)
            mock_print.assert_called_once()
            panel = mock_print.call_args[0][0]
            assert panel.border_style == "red"

    def test_long_output_truncated(self):
        app = make_app()
        long_output = "\n".join([f"line {i}" for i in range(100)])
        with patch.object(app.console, "print") as mock_print:
            app.show_tool_result(long_output)
            panel = mock_print.call_args[0][0]
            assert "50 more lines" in str(panel.renderable)


class TestErrorRendering:
    """错误渲染测试"""

    def test_show_error(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.show_error("something went wrong")
            mock_print.assert_called_once()
            assert "something went wrong" in str(mock_print.call_args)


class TestEventDispatch:
    """事件分发测试"""

    def test_handle_text_event(self):
        app = make_app()
        event = StreamEvent(type="text", content="hello")
        with patch.object(app, "render_stream_chunk") as mock:
            app._handle_event(event)
            mock.assert_called_once_with("hello")

    def test_handle_tool_call_event(self):
        app = make_app()
        event = StreamEvent(
            type="tool_call",
            tool_name="file_read",
            tool_input={"path": "test.py"},
        )
        with patch.object(app, "flush_stream") as mock_flush, \
             patch.object(app, "show_tool_call") as mock_call:
            app._handle_event(event)
            mock_flush.assert_called_once()
            mock_call.assert_called_once_with("file_read", {"path": "test.py"})

    def test_handle_tool_result_event(self):
        app = make_app()
        event = StreamEvent(type="tool_result", content="output", is_error=False)
        with patch.object(app, "show_tool_result") as mock:
            app._handle_event(event)
            mock.assert_called_once_with("output", False)

    def test_handle_tool_result_error_event(self):
        app = make_app()
        event = StreamEvent(type="tool_result", content="error", is_error=True)
        with patch.object(app, "show_tool_result") as mock:
            app._handle_event(event)
            mock.assert_called_once_with("error", True)

    def test_handle_unknown_event(self):
        app = make_app()
        event = StreamEvent(type="unknown", content="data")
        app._handle_event(event)  # 不崩溃


class TestRunLoop:
    """主循环测试"""

    def test_run_exits_on_exit_command(self):
        app = make_app()
        with patch.object(app, "get_input", side_effect=["/exit"]), \
             patch.object(app, "show_header"), \
             patch.object(app.console, "print"):
            app.run()

    def test_run_exits_on_eof(self):
        app = make_app()
        with patch.object(app, "get_input", side_effect=EOFError), \
             patch.object(app, "show_header"), \
             patch.object(app.console, "print"):
            app.run()

    def test_run_handles_keyboard_interrupt(self):
        app = make_app()
        call_count = 0

        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise KeyboardInterrupt
            return "/exit"

        with patch.object(app, "get_input", side_effect=side_effect), \
             patch.object(app, "show_header"), \
             patch.object(app.console, "print"):
            app.run()
        assert call_count == 2

    def test_run_skips_empty_input(self):
        app = make_app()
        with patch.object(app, "get_input", side_effect=["", "  ", "/exit"]), \
             patch.object(app, "show_header"), \
             patch.object(app, "on_message") as mock_callback, \
             patch.object(app.console, "print"):
            app.run()
        mock_callback.assert_not_called()

    def test_run_calls_on_message(self):
        events = [StreamEvent(type="text", content="response")]

        def on_message(msg: str) -> Iterator[StreamEvent]:
            return iter(events)

        app = AgentApp(on_message=on_message)

        with patch.object(app, "get_input", side_effect=["hello", "/exit"]), \
             patch.object(app, "show_header"), \
             patch.object(app, "_handle_event") as mock_handle, \
             patch.object(app.console, "print"):
            app.run()
        mock_handle.assert_called_once()

    def test_run_handles_callback_error(self):
        def on_message(msg: str) -> Iterator[StreamEvent]:
            raise ValueError("callback error")

        app = AgentApp(on_message=on_message)

        with patch.object(app, "get_input", side_effect=["hello", "/exit"]), \
             patch.object(app, "show_header"), \
             patch.object(app, "show_error") as mock_error, \
             patch.object(app.console, "print"):
            app.run()
        mock_error.assert_called_once_with("callback error")


class TestStatus:
    """状态栏测试"""

    def test_show_status(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.show_status("? for shortcuts")
            mock_print.assert_called_once()


class TestWelcome:
    """欢迎信息测试"""

    def test_show_welcome(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.show_welcome()
            mock_print.assert_called_once()


class TestResponse:
    """回复渲染测试"""

    def test_show_response(self):
        app = make_app()
        with patch.object(app.console, "print") as mock_print:
            app.show_response("# Hello")
            mock_print.assert_called_once()
            from rich.markdown import Markdown
            assert isinstance(mock_print.call_args[0][0], Markdown)
