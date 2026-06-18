"""
F01 模型层测试

测试场景:
1. 配置加载：从环境变量正确读取
2. 客户端初始化：正确创建 anthropic 客户端
3. 同步对话：返回正确文本
4. 流式对话：逐块返回文本
5. 重试机制：超时时自动重试
6. 错误处理：认证错误不重试，直接抛出
"""

import os
import pytest
from unittest.mock import MagicMock, patch

import anthropic
from dotenv import load_dotenv

from agent.core.model import ModelConfig, MimoClient, load_config

# 加载 .env 文件（集成测试需要）
load_dotenv()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """每个测试前清除 .env 的影响，确保环境变量干净。"""
    for key in ("MIMO_API_KEY", "MIMO_BASE_URL", "MIMO_MODEL"):
        monkeypatch.delenv(key, raising=False)


class TestModelConfig:
    """ModelConfig 配置类测试"""

    def test_default_values(self):
        """默认值正确"""
        config = ModelConfig(api_key="test-key")
        assert config.api_key == "test-key"
        assert config.base_url == "https://token-plan-cn.xiaomimimo.com/anthropic"
        assert config.model == "mimo-v2.5-pro"
        assert config.max_tokens == 4096
        assert config.timeout == 60.0
        assert config.max_retries == 3
        assert config.retry_delay == 1.0

    def test_custom_values(self):
        """可以自定义配置"""
        config = ModelConfig(
            api_key="custom-key",
            base_url="https://custom-url.com",
            model="custom-model",
            max_tokens=2048,
            timeout=30.0,
            max_retries=5,
            retry_delay=2.0,
        )
        assert config.api_key == "custom-key"
        assert config.base_url == "https://custom-url.com"
        assert config.model == "custom-model"
        assert config.max_tokens == 2048
        assert config.timeout == 30.0
        assert config.max_retries == 5
        assert config.retry_delay == 2.0


class TestLoadConfig:
    """load_config 配置加载测试"""

    def test_load_from_env(self, monkeypatch):
        """从环境变量正确加载"""
        monkeypatch.setenv("MIMO_API_KEY", "test-api-key")
        monkeypatch.setenv("MIMO_BASE_URL", "https://test-url.com")
        monkeypatch.setenv("MIMO_MODEL", "test-model")

        config = load_config()
        assert config.api_key == "test-api-key"
        assert config.base_url == "https://test-url.com"
        assert config.model == "test-model"

    def test_load_with_defaults(self, monkeypatch):
        """未设置可选环境变量时使用默认值"""
        monkeypatch.setenv("MIMO_API_KEY", "test-api-key")
        monkeypatch.delenv("MIMO_BASE_URL", raising=False)
        monkeypatch.delenv("MIMO_MODEL", raising=False)

        config = load_config()
        assert config.api_key == "test-api-key"
        assert config.base_url == "https://token-plan-cn.xiaomimimo.com/anthropic"
        assert config.model == "mimo-v2.5-pro"

    def test_missing_api_key_raises_error(self, monkeypatch):
        """未设置 API key 时抛出 ValueError"""
        monkeypatch.delenv("MIMO_API_KEY", raising=False)
        # mock load_dotenv 防止它从 .env 文件重新加载
        with patch("agent.core.model.load_dotenv"):
            with pytest.raises(ValueError, match="MIMO_API_KEY"):
                load_config()


class TestMimoClient:
    """MimoClient 客户端测试"""

    @pytest.fixture
    def config(self):
        """测试用配置"""
        return ModelConfig(api_key="test-key", max_retries=2, retry_delay=0.1)

    @pytest.fixture
    def client(self, config):
        """测试用客户端"""
        return MimoClient(config)

    def test_init(self, client, config):
        """初始化正确"""
        assert client.config == config
        assert client._client is not None

    def test_chat_returns_reply(self, client):
        """同步对话返回正确文本"""
        # Mock anthropic client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="你好！")]
        client._client.messages.create = MagicMock(return_value=mock_response)

        reply = client.chat([{"role": "user", "content": "你好"}])
        assert reply == "你好！"
        client._client.messages.create.assert_called_once()

    def test_chat_with_system_prompt(self, client):
        """带 system prompt 的对话"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="好的")]
        client._client.messages.create = MagicMock(return_value=mock_response)

        reply = client.chat(
            messages=[{"role": "user", "content": "测试"}],
            system="你是一个测试助手"
        )
        assert reply == "好的"
        # 验证 system 参数被传递
        call_kwargs = client._client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == "你是一个测试助手"

    def test_chat_stream_yields_chunks(self, client):
        """流式对话逐块返回文本"""
        # Mock stream context manager
        mock_stream = MagicMock()
        mock_stream.text_stream = ["你", "好", "！"]
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        client._client.messages.stream = MagicMock(return_value=mock_stream)

        chunks = list(client.chat_stream([{"role": "user", "content": "你好"}]))
        assert chunks == ["你", "好", "！"]
        assert "".join(chunks) == "你好！"

    def test_retry_on_rate_limit(self, client):
        """限流时自动重试"""
        # 第一次抛出限流错误，第二次成功
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="成功")]

        client._client.messages.create = MagicMock(
            side_effect=[anthropic.RateLimitError("rate limited", response=MagicMock(), body=None), mock_response]
        )

        reply = client.chat([{"role": "user", "content": "测试"}])
        assert reply == "成功"
        assert client._client.messages.create.call_count == 2

    def test_retry_on_timeout(self, client):
        """超时时自动重试"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="成功")]

        client._client.messages.create = MagicMock(
            side_effect=[anthropic.APITimeoutError("timeout"), mock_response]
        )

        reply = client.chat([{"role": "user", "content": "测试"}])
        assert reply == "成功"
        assert client._client.messages.create.call_count == 2

    def test_retry_on_connection_error(self, client):
        """连接错误时自动重试"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="成功")]

        client._client.messages.create = MagicMock(
            side_effect=[anthropic.APIConnectionError(request=MagicMock()), mock_response]
        )

        reply = client.chat([{"role": "user", "content": "测试"}])
        assert reply == "成功"
        assert client._client.messages.create.call_count == 2

    def test_no_retry_on_auth_error(self, client):
        """认证错误不重试"""
        client._client.messages.create = MagicMock(
            side_effect=anthropic.AuthenticationError("invalid key", response=MagicMock(), body=None)
        )

        with pytest.raises(anthropic.AuthenticationError):
            client.chat([{"role": "user", "content": "测试"}])
        # 只调用一次，不重试
        assert client._client.messages.create.call_count == 1

    def test_no_retry_on_api_error(self, client):
        """其他 API 错误不重试"""
        client._client.messages.create = MagicMock(
            side_effect=anthropic.APIError("api error", request=MagicMock(), body=None)
        )

        with pytest.raises(anthropic.APIError):
            client.chat([{"role": "user", "content": "测试"}])
        assert client._client.messages.create.call_count == 1

    def test_max_retries_exhausted(self, client):
        """重试次数用完后抛出异常"""
        client._client.messages.create = MagicMock(
            side_effect=anthropic.RateLimitError("rate limited", response=MagicMock(), body=None)
        )

        with pytest.raises(anthropic.RateLimitError):
            client.chat([{"role": "user", "content": "测试"}])
        # max_retries=2，所以调用 2 次
        assert client._client.messages.create.call_count == 2


class TestMimoClientIntegration:
    """集成测试 - 需要真实 API key

    设置环境变量 MIMO_API_KEY 后运行:
        MIMO_API_KEY=xxx pytest tests/test_model.py -v -k Integration
    """

    @pytest.fixture
    def client(self):
        """真实客户端（如果有 API key）"""
        api_key = os.environ.get("MIMO_API_KEY")
        if not api_key:
            pytest.skip("MIMO_API_KEY not set")
        config = ModelConfig(api_key=api_key)
        return MimoClient(config)

    def test_chat_returns_reply(self, client):
        """能连接 API 并收到非空回复"""
        reply = client.chat([{"role": "user", "content": "说'你好'"}])
        assert len(reply) > 0
        assert isinstance(reply, str)

    def test_multi_turn_context(self, client):
        """多轮对话能保持上下文"""
        messages = [
            {"role": "user", "content": "记住这个数字: 42"},
            {"role": "assistant", "content": "好的，我记住了数字 42。"},
            {"role": "user", "content": "我让你记住的数字是多少？"},
        ]
        reply = client.chat(messages)
        assert "42" in reply

    def test_stream_yields_chunks(self, client):
        """流式输出逐块返回，拼接后是完整回复"""
        chunks = list(client.chat_stream([{"role": "user", "content": "说一句话"}]))
        assert len(chunks) > 0
        full = "".join(chunks)
        assert len(full) > 0
