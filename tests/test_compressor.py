"""
F10 上下文压缩器测试

测试场景:
1. Happy path: 10 条消息，保留最近 3 条，其余压缩成摘要
2. Edge case: 所有消息都很短，不需要压缩
3. Edge case: 单条消息很长（工具输出），估算 token 准确
4. Error case: LLM 调用失败时，返回原始消息（不压缩）
5. Integration: 压缩后的消息格式正确，包含 [摘要] 标记
"""

from unittest.mock import MagicMock

import pytest

from agent.context.compressor import ContextCompressor
from agent.core.model import MimoClient


@pytest.fixture
def mock_client():
    """Mock MimoClient"""
    client = MagicMock(spec=MimoClient)
    return client


@pytest.fixture
def compressor(mock_client):
    """ContextCompressor 实例"""
    return ContextCompressor(mock_client)


def _make_messages(count: int, content_length: int = 100) -> list[dict]:
    """创建测试消息

    Args:
        count: 消息数量
        content_length: 每条消息的长度

    Returns:
        消息列表
    """
    messages = []
    for i in range(count):
        role = "user" if i % 2 == 0 else "assistant"
        content = f"消息 {i}: " + "x" * (content_length - 10)
        messages.append({"role": role, "content": content})
    return messages


class TestContextCompressor:
    """压缩器核心测试"""

    def test_compress_empty_messages(self, compressor):
        """空消息列表不需要压缩"""
        result = compressor.compress([], keep_tokens=1000)
        assert result == []

    def test_compress_short_messages_no_compression(self, compressor):
        """所有消息都很短，不需要压缩"""
        messages = _make_messages(5, content_length=50)  # 每条约 12 tokens
        # keep_tokens 足够大，不需要压缩
        result = compressor.compress(messages, keep_tokens=10000)
        assert result == messages

    def test_compress_10_messages_keep_recent(self, compressor, mock_client):
        """10 条消息，保留最近几条，其余压缩"""
        # 每条消息约 250 tokens (1000 chars / 4)
        messages = _make_messages(10, content_length=1000)

        # keep_tokens=1000 约保留 4 条消息
        mock_client.chat.return_value = "这是摘要内容"
        result = compressor.compress(messages, keep_tokens=1000)

        # 应该有摘要消息 + 保留的消息
        assert len(result) < len(messages)
        assert result[0]["role"] == "assistant"
        assert "[摘要]" in result[0]["content"]

    def test_compress_preserves_recent_messages(self, compressor, mock_client):
        """压缩后保留最近的消息内容不变"""
        messages = _make_messages(10, content_length=1000)

        mock_client.chat.return_value = "摘要"
        result = compressor.compress(messages, keep_tokens=1000)

        # 最后的几条消息应该保持原样
        recent_in_result = result[1:]  # 跳过摘要消息
        for msg in recent_in_result:
            assert msg in messages

    def test_compress_llm_failure_returns_fallback(self, compressor, mock_client):
        """LLM 调用失败时，返回降级摘要"""
        messages = _make_messages(10, content_length=1000)

        mock_client.chat.side_effect = Exception("API error")
        result = compressor.compress(messages, keep_tokens=1000)

        # 应该有摘要消息（降级版本）
        assert len(result) < len(messages)
        assert "[压缩失败" in result[0]["content"]

    def test_compress_with_tool_result_messages(self, compressor, mock_client):
        """包含 tool_result 的消息也能正确压缩"""
        messages = [
            {"role": "user", "content": "读取文件"},
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "content": "文件内容很长" * 100}
                ],
            },
            {"role": "assistant", "content": "我看到了文件内容"},
            {"role": "user", "content": "继续" * 50},
            {"role": "assistant", "content": "好的" * 50},
        ]

        mock_client.chat.return_value = "摘要"
        result = compressor.compress(messages, keep_tokens=100)

        # 应该压缩了前面的消息
        assert result[0]["role"] == "assistant"
        assert "[摘要]" in result[0]["content"]


class TestEstimateTokens:
    """Token 估算测试"""

    def test_estimate_empty_string(self, compressor):
        """空字符串估算为 0"""
        assert compressor._estimate_tokens("") == 0

    def test_estimate_short_text(self, compressor):
        """短文本估算"""
        # 4 字符 ≈ 1 token
        assert compressor._estimate_tokens("hello") == 1  # 5 chars / 4 = 1

    def test_estimate_long_text(self, compressor):
        """长文本估算"""
        text = "a" * 1000
        assert compressor._estimate_tokens(text) == 250  # 1000 / 4 = 250


class TestFindSplitPoint:
    """分割点测试"""

    def test_split_point_all_short_messages(self, compressor):
        """所有消息都很短，分割点为 0"""
        messages = _make_messages(5, content_length=40)  # 每条约 10 tokens
        split = compressor._find_split_point(messages, keep_tokens=1000)
        assert split == 0

    def test_split_point_keeps_recent(self, compressor):
        """分割点正确保留最近的消息"""
        # 每条消息 250 tokens
        messages = _make_messages(10, content_length=1000)
        # keep_tokens=1000 约保留 4 条
        split = compressor._find_split_point(messages, keep_tokens=1000)
        assert split > 0
        assert split < len(messages)


class TestFormatMessages:
    """消息格式化测试"""

    def test_format_simple_messages(self, compressor):
        """格式化简单消息"""
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
        ]
        result = compressor._format_messages(messages)
        assert "[user]: 你好" in result
        assert "[assistant]: 你好！" in result

    def test_format_tool_result_message(self, compressor):
        """格式化包含 tool_result 的消息"""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "content": "工具输出"}
                ],
            }
        ]
        result = compressor._format_messages(messages)
        assert "工具输出" in result
