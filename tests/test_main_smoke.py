"""main.py 默认入口 smoke test。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.cli.app import AgentApp
from agent.core.loop import AgentLoop
from agent.core.model import ModelConfig
from agent.core.model import StreamResult
from agent.main import (
    create_agent_app,
    create_agent_loop,
    create_default_registry,
)


class FakeClient:
    """用于 smoke test 的本地 fake client。"""

    def chat_stream(self, messages, system="", tools=None):
        return StreamResult(
            text=iter(["ok"]),
            content_blocks=[{"type": "text", "text": "ok"}],
        )

    def chat(self, messages, system="", tools=None):
        return "summary"


def test_create_default_registry_has_base_tools():
    registry = create_default_registry()
    names = {tool.name for tool in registry.get_all()}
    assert {"bash", "read", "write", "edit", "grep", "glob"} <= names


def test_create_agent_loop_registers_base_tools_and_subagent(tmp_path):
    loop = create_agent_loop(
        FakeClient(),  # type: ignore[arg-type]
        model="test-model",
        workspace_root=str(tmp_path),
    )

    names = {tool.name for tool in loop._registry.get_all()}
    assert {"bash", "read", "write", "edit", "grep", "glob", "subagent"} <= names
    assert loop._config.workspace_root == str(tmp_path)
    assert loop._config.model == "test-model"


def test_create_agent_app_mounts_confirmation_handler(tmp_path):
    loop = create_agent_loop(
        FakeClient(),  # type: ignore[arg-type]
        model="test-model",
        workspace_root=str(tmp_path),
    )

    app = create_agent_app(loop, model="test-model")

    handler = loop._config.permission_handler
    assert isinstance(app, AgentApp)
    assert handler is not None
    assert getattr(handler, "__self__", None) is app
    assert getattr(handler, "__func__", None) is app.confirm_permission.__func__


def test_smoke_reset_command_calls_real_loop_reset(tmp_path):
    loop = create_agent_loop(
        FakeClient(),  # type: ignore[arg-type]
        model="test-model",
        workspace_root=str(tmp_path),
    )
    loop._messages.append({"role": "user", "content": "hello"})
    loop._turn_count = 3

    app = create_agent_app(loop, model="test-model")
    with patch.object(app.console, "print"):
        handled = app._handle_command("/reset")

    assert handled is True
    assert loop.messages == []
    assert loop.turn_count == 0


def test_smoke_compact_command_calls_real_loop_compact(tmp_path):
    loop = create_agent_loop(
        FakeClient(),  # type: ignore[arg-type]
        model="test-model",
        workspace_root=str(tmp_path),
    )
    loop._messages = [
        {"role": "user", "content": "old message"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "recent message"},
    ]

    app = create_agent_app(loop, model="test-model")
    with patch.object(app.console, "print"):
        handled = app._handle_command("/compact")

    assert handled is True
    assert len(loop.messages) >= 1
    assert loop.token_count == 0


def test_create_agent_app_uses_ascii_fallback_on_non_utf8_console(tmp_path):
    fake_console = MagicMock()
    fake_console.file = SimpleNamespace(encoding="cp936")

    loop = create_agent_loop(
        FakeClient(),  # type: ignore[arg-type]
        model="test-model",
        workspace_root=str(tmp_path),
    )

    with patch("agent.cli.app.Console", return_value=fake_console):
        app = create_agent_app(loop, model="test-model")

    assert app._use_ascii_ui is True
    assert app._prompt_symbol == ">"


def test_main_exits_cleanly_when_api_key_missing(monkeypatch):
    with patch("agent.main.load_config", side_effect=ValueError("missing key")), \
         patch("builtins.print") as mock_print:
        with pytest.raises(SystemExit) as exc_info:
            from agent.main import main

            main()

    assert exc_info.value.code == 1
    printed = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
    assert "MIMO_API_KEY" in printed


def test_main_smoke_wires_default_entry_without_remote_call(monkeypatch, tmp_path):
    import agent.main as main_module

    captured: dict[str, object] = {}
    config = ModelConfig(api_key="test-key", model="test-model")

    def fake_mimo_client(received_config: ModelConfig) -> FakeClient:
        captured["config"] = received_config
        return FakeClient()

    def fake_run(self: AgentApp) -> None:
        captured["app"] = self

    monkeypatch.setattr(main_module, "load_config", lambda: config)
    monkeypatch.setattr(main_module, "MimoClient", fake_mimo_client)
    monkeypatch.setattr(main_module.os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(AgentApp, "run", fake_run)

    main_module.main()

    assert captured["config"] is config

    app = captured["app"]
    assert isinstance(app, AgentApp)
    assert app.model == "test-model"

    loop = getattr(app.on_reset, "__self__", None)
    assert isinstance(loop, AgentLoop)
    assert loop._config.workspace_root == str(tmp_path)

    names = {tool.name for tool in loop._registry.get_all()}
    assert {"bash", "read", "write", "edit", "grep", "glob", "subagent"} <= names

    handler = loop._config.permission_handler
    assert handler is not None
    assert getattr(handler, "__self__", None) is app
    assert getattr(handler, "__func__", None) is app.confirm_permission.__func__
