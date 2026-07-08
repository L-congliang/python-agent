"""FakeModelClient / ScriptedModelClient - 脚本化模型，用于确定性测试。"""

from __future__ import annotations

from typing import Any

from agent.core.model import StreamResult


class ScriptedModelClient:
    """脚本化模型客户端，支持 tool_use 行为脚本。

    接受预定义的 "轮次" 列表，每次 chat_stream() 返回下一个轮次的 content_blocks。
    轮次可以包含 tool_use 块（触发工具执行）或纯 text 块（最终回复）。

    用法:
        client = ScriptedModelClient([
            # Round 1: 调用 file_read
            [{"type": "tool_use", "id": "call_1", "name": "read", "input": {"file_path": "/src/main.py"}}],
            # Round 2: 最终回复
            [{"type": "text", "text": "The file contains a main function."}],
        ])
    """

    def __init__(self, rounds: list[list[dict[str, Any]]]) -> None:
        self._rounds = list(rounds)
        self._index = 0
        self.prompts: list[str] = []
        self.supports_prompt_cache: bool = False
        self.last_completion_metadata: dict[str, Any] = {}

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        **kwargs: Any,
    ) -> StreamResult:
        """返回下一个轮次的 content_blocks。"""
        # 记录 prompt 用于调试
        prompt = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                prompt = str(msg.get("content", ""))
                break
        self.prompts.append(prompt)

        if self._index < len(self._rounds):
            content_blocks = self._rounds[self._index]
            self._index += 1
        else:
            # 轮次用尽，返回默认文本
            content_blocks = [{"type": "text", "text": "Task completed."}]

        # 从 content_blocks 中提取文本用于 StreamResult.text
        text_parts = [
            b.get("text", "") for b in content_blocks if b.get("type") == "text"
        ]
        text = "".join(text_parts) if text_parts else ""

        return StreamResult(
            text=iter([text]) if text else iter([]),
            content_blocks=content_blocks,
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    def complete(
        self,
        prompt: str,
        max_new_tokens: int,
        **kwargs: Any,
    ) -> str:
        """简单接口（不支持，抛出异常）。"""
        raise NotImplementedError(
            "ScriptedModelClient only supports chat_stream(), not complete()."
        )


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
        **kwargs: Any,
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


class PromptAwareScriptedModelClient:
    """根据 reflection prompt 中的 retry_strategy 字段选择不同 retry branch。

    用于 Phase 3.2F prompt-sensitive benchmark。
    解析最后一条 user message 中的 "retry_strategy: xxx" 行，
    选对应的 branch rounds 执行。

    用法:
        client = PromptAwareScriptedModelClient(
            branches={
                "use_memory_answer": [rounds...],
                "reread_then_answer": [rounds...],
            },
            default_branch="use_memory_answer",
        )
    """

    def __init__(
        self,
        branches: dict[str, list[list[dict[str, Any]]]],
        default_branch: str,
    ) -> None:
        self._branches = branches
        self._default_branch = default_branch
        self._index = 0
        self.prompts: list[str] = []
        self.supports_prompt_cache: bool = False
        self.last_completion_metadata: dict[str, Any] = {}
        self._selected_branch: str = default_branch

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        **kwargs: Any,
    ) -> StreamResult:
        """返回下一个轮次的 content_blocks，根据 retry_strategy 选 branch。"""
        # 记录 prompt
        prompt = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                prompt = str(msg.get("content", ""))
                break
        self.prompts.append(prompt)

        # 首次调用时：从 prompt 解析 retry_strategy
        if self._index == 0:
            self._selected_branch = self._extract_strategy(prompt)

        # 用选中的 branch 执行
        branch_rounds = self._branches.get(
            self._selected_branch,
            self._branches[self._default_branch],
        )

        if self._index < len(branch_rounds):
            content_blocks = branch_rounds[self._index]
            self._index += 1
        else:
            content_blocks = [{"type": "text", "text": "Task completed."}]

        # 从 content_blocks 提取文本
        text_parts = [
            b.get("text", "") for b in content_blocks if b.get("type") == "text"
        ]
        text = "".join(text_parts) if text_parts else ""

        return StreamResult(
            text=iter([text]) if text else iter([]),
            content_blocks=content_blocks,
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    def _extract_strategy(self, prompt: str) -> str:
        """从 prompt 中提取 retry_strategy 字段"""
        for line in prompt.split("\n"):
            stripped = line.strip()
            if stripped.startswith("retry_strategy:"):
                strategy = stripped.split(":", 1)[1].strip()
                if strategy in self._branches:
                    return strategy
        return self._default_branch

    def complete(
        self,
        prompt: str,
        max_new_tokens: int,
        **kwargs: Any,
    ) -> str:
        """简单接口（不支持）"""
        raise NotImplementedError(
            "PromptAwareScriptedModelClient only supports chat_stream()."
        )
