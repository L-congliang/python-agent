"""FakeModelClient - 脚本化模型，用于确定性测试。"""

from __future__ import annotations

from typing import Any

from agent.core.model import StreamResult


class FakeModelClient:
    """脚本化模型客户端。

    接受预定义的输出列表，每次调用 complete() 或 chat_stream() 返回下一个输出。
    不调用真实 API，100% 确定性。

    支持两种接口：
    - complete(prompt, max_new_tokens) → str：简单接口
    - chat_stream(messages, system) → StreamResult：兼容 AgentLoop 的流式接口
    """

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.prompts: list[str] = []
        self.supports_prompt_cache: bool = False
        self.last_completion_metadata: dict[str, Any] = {}

    def complete(
        self,
        prompt: str,
        max_new_tokens: int,
        **kwargs: Any,
    ) -> str:
        """返回下一个预定义输出（简单接口）。"""
        self.prompts.append(prompt)
        if not self.outputs:
            raise RuntimeError("FakeModelClient: output list exhausted")
        return self.outputs.pop(0)

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
    ) -> StreamResult:
        """返回 StreamResult，兼容 AgentLoop 的流式接口。

        AgentLoop 调用 self._client.chat_stream(messages, system=system)，
        需要返回一个 StreamResult 对象。

        StreamResult 包含：
        - text: 文本 chunk 迭代器（AgentLoop 会 list() 消费它）
        - content_blocks: content block 列表（用于 adapter.parse_response）
        - usage: token 使用量（可选）
        """
        # 从消息列表中提取最后一条用户消息作为 prompt
        prompt = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                prompt = str(msg.get("content", ""))
                break

        self.prompts.append(prompt)

        if not self.outputs:
            raise RuntimeError("FakeModelClient: output list exhausted")

        response = self.outputs.pop(0)

        # 构造 content_blocks 格式（兼容 mimo adapter 的 parse_response）
        # mimo adapter 从 content_blocks 中找 type="text" 的 block
        content_blocks = [
            {
                "type": "text",
                "text": response,
            }
        ]

        return StreamResult(
            text=iter([response]),  # 把字符串变成单元素迭代器
            content_blocks=content_blocks,
            usage={"input_tokens": 0, "output_tokens": 0},
        )
