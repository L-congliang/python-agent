"""端到端测试 - 验证完整链路

用户输入 → CLI → AgentLoop → mimo API → tool_use → 工具执行 → 结果注入 → 回复

运行方式:
    uv run python -m pytest tests/e2e_test.py -v -s
"""

from __future__ import annotations

import os
import sys

import pytest
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

from agent.core.model import MimoClient, ModelConfig
from agent.core.loop import AgentLoop, LoopConfig
from agent.tools.registry import ToolRegistry
from agent.tools.bash import bash_tool
from agent.tools.glob import glob_tool
from agent.tools.file_read import file_read_tool


# 跳过条件：没有 API key 时跳过
pytestmark = pytest.mark.skipif(
    not os.environ.get("MIMO_API_KEY"),
    reason="MIMO_API_KEY not set",
)


@pytest.fixture
def client():
    """创建 MimoClient"""
    config = ModelConfig(
        api_key=os.environ["MIMO_API_KEY"],
        base_url=os.environ.get(
            "MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/anthropic"
        ),
        model=os.environ.get("MIMO_MODEL", "mimo-v2.5-pro"),
    )
    return MimoClient(config)


@pytest.fixture
def registry():
    """创建工具注册表"""
    reg = ToolRegistry()
    reg.register(bash_tool)
    reg.register(glob_tool)
    reg.register(file_read_tool)
    return reg


class TestModelLayer:
    """F01: 模型层基础测试"""

    def test_simple_chat(self, client):
        """模型能正常回复"""
        result = client.chat(
            messages=[{"role": "user", "content": "Say 'hello' and nothing else."}],
            system="You are a helpful assistant. Respond concisely.",
        )
        assert isinstance(result, str)
        assert len(result) > 0
        print(f"\n  Model reply: {result[:100]}")

    def test_stream_chat(self, client):
        """流式调用正常"""
        stream = client.chat_stream(
            messages=[{"role": "user", "content": "Say 'ok'."}],
            system="Respond with one word.",
        )
        chunks = list(stream.text)
        assert len(chunks) > 0
        full = "".join(chunks)
        assert len(full) > 0
        print(f"\n  Stream reply: {full[:100]}")


class TestToolProtocol:
    """F03+F08+F11: 工具协议测试"""

    def test_tool_registry_has_tools(self, registry):
        """注册表包含工具"""
        tools = registry.get_enabled_tools()
        assert len(tools) >= 3  # bash, glob, file_read
        names = [t.name for t in tools]
        assert "bash" in names
        assert "glob" in names
        assert "read" in names  # file_read tool registered as "read"

    def test_to_anthropic_tools(self, registry):
        """工具能转换为 Anthropic 格式"""
        anthropic_tools = registry.to_anthropic_tools()
        assert len(anthropic_tools) >= 3
        for tool in anthropic_tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool


class TestAgentLoop:
    """F04: Agent 主循环测试"""

    def test_simple_text_response(self, client, registry):
        """纯文本对话（无工具调用）"""
        loop = AgentLoop(client, registry, LoopConfig(max_turns=3))
        result = loop.run("Say 'test passed' and nothing else.")
        assert isinstance(result, str)
        assert len(result) > 0
        print(f"\n  Loop reply: {result[:200]}")

    def test_tool_use_bash(self, client, registry):
        """工具调用：Bash 执行命令"""
        loop = AgentLoop(client, registry, LoopConfig(max_turns=5))
        result = loop.run("Run the command: echo 'hello from bash'")
        assert "hello" in result.lower() or "bash" in result.lower()
        print(f"\n  Bash tool reply: {result[:300]}")

    def test_tool_use_glob(self, client, registry):
        """工具调用：Glob 查找文件"""
        loop = AgentLoop(client, registry, LoopConfig(max_turns=5))
        result = loop.run("Find all Python files in the tests/ directory using the glob tool.")
        assert ".py" in result
        print(f"\n  Glob tool reply: {result[:300]}")

    def test_multi_turn(self, client, registry):
        """多轮对话 + 工具调用"""
        loop = AgentLoop(client, registry, LoopConfig(max_turns=8))
        result = loop.run(
            "First, list all .py files in src/agent/tools/ using glob. "
            "Then, tell me how many files you found."
        )
        assert isinstance(result, str)
        assert len(result) > 0
        print(f"\n  Multi-turn reply: {result[:400]}")
