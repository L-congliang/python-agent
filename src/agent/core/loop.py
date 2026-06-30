"""
Agent 主循环 - 对齐 Claude Code 的 query.ts

核心循环：用户输入 → 模型回复 → 工具调用 → 结果返回 → 循环

设计决策:
- 为什么用 class 而不是函数？
  因为循环需要维护状态（消息历史、轮次计数、中断状态）。
  class 可以把这些状态封装在一起。

- 为什么不直接在 chat() 里循环？
  因为 chat() 是一次对话，loop() 是多轮循环。
  分离关注点：model.py 只管 API 调用，loop.py 管流程控制。

- 为什么需要 AbortController？
  因为用户可能在工具执行过程中按 Ctrl+C，
  需要优雅地取消而不是直接崩溃。

- 为什么用 ModelAdapter？
  不同模型（mimo、DeepSeek）的响应格式有差异（ThinkingBlock、工具调用格式等）。
  适配器把这些差异封装起来，AgentLoop 只依赖统一接口。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from agent.core.model import MimoClient
from agent.core.model_adapter import ModelAdapter, ToolCall as AdapterToolCall
from agent.core.types import (
    Message,
    Role,
    ToolCall,
    ToolCallResult,
    ToolResult,
)
from agent.core.context import ToolUseContext, AbortController, FileReadState
from agent.context.compressor import ContextCompressor
from agent.context.manager import ContextManager, ContextMetadata
from agent.memory.manager import MemoryManager
from agent.tools.registry import ToolRegistry

logger = logging.getLogger("agent.loop")


@dataclass
class LoopConfig:
    """主循环配置

    对齐 Claude Code 的 QueryParams。
    控制循环行为的所有参数。
    """

    # 模型配置
    model: str = "mimo-v2.5-pro"
    max_tokens: int = 4096  # 单次回复最大 token 数

    # 上下文窗口
    context_window: int = 128_000  # 上下文窗口大小（用于压缩判断）

    # 循环控制
    max_turns: int = 50  # 最大轮次（防止无限循环）
    max_tool_calls: int = 100  # 最大工具调用次数

    # 系统提示
    system_prompt: str = ""
    append_system_prompt: str = ""  # 追加的系统提示

    # 回调
    on_notify: Callable[[str], None] | None = None  # 通知回调

    # 调试
    debug: bool = False
    verbose: bool = False


class AgentLoop:
    """Agent 主循环

    核心循环：用户输入 → 模型回复 → 工具调用 → 结果返回 → 循环

    使用方式:
        client = MimoClient(config)
        adapter = MimoAdapter()
        registry = ToolRegistry()
        # ... 注册工具 ...
        loop = AgentLoop(client, registry, adapter=adapter)

        # 同步运行
        reply = loop.run("帮我写一个 hello world")

        # 流式运行
        for chunk in loop.run_stream("帮我写一个 hello world"):
            print(chunk, end="", flush=True)
    """

    def __init__(
        self,
        client: MimoClient,
        registry: ToolRegistry,
        config: LoopConfig | None = None,
        adapter: ModelAdapter | None = None,
    ) -> None:
        """初始化主循环

        Args:
            client: mimo API 客户端（负责 SDK 调用，包括流式）
            registry: 工具注册表
            config: 循环配置（可选，有默认值）
            adapter: 模型适配器（负责解析响应差异）。如果为 None，使用默认的 mimo 适配器。
        """
        self._client = client
        self._registry = registry
        self._config = config or LoopConfig()
        self._messages: list[dict[str, Any]] = []
        self._turn_count: int = 0
        self._tool_call_count: int = 0
        self._abort_controller = AbortController()
        self._file_read_state = FileReadState()
        # Token 追踪
        self._total_tokens: int = 0
        self._compressor = ContextCompressor(client)
        # 上下文管理器（预算制 prompt 组装）
        self._context_manager = ContextManager()
        self._last_context_metadata: ContextMetadata | None = None
        # 记忆管理器
        self._memory = MemoryManager()
        self._memory.load()
        # 模型适配器（延迟导入，避免循环依赖）
        self._adapter: ModelAdapter
        if adapter is None:
            from agent.core.adapters.mimo_adapter import MimoAdapter
            self._adapter = MimoAdapter()
        else:
            self._adapter = adapter

    def run(self, user_input: str) -> str:
        """运行一轮完整的对话（同步）

        流程:
        1. 构建消息（历史 + 用户输入）
        2. 调用模型（内部用 chat_stream 获取 content_blocks）
        3. 解析响应（文本 + tool_use）
        4. 如果有 tool_use → 执行工具 → 注入结果 → 回到步骤 2
        5. 如果没有 tool_use → 返回模型回复

        Args:
            user_input: 用户输入的文本

        Returns:
            模型的最终回复文本

        Raises:
            KeyboardInterrupt: 用户中断（Ctrl+C）
        """
        # 添加用户消息
        self._messages.append({"role": "user", "content": user_input})

        while self._turn_count < self._config.max_turns:
            # 检查中断
            if self._abort_controller.is_aborted:
                raise KeyboardInterrupt("Agent loop aborted")

            # 调用模型（内部用 chat_stream 获取 content_blocks）
            system = self._build_system_prompt()
            logger.info("Turn %d: calling model", self._turn_count + 1)

            try:
                stream_result = self._client.chat_stream(
                    self._messages, system=system
                )
                # 消费所有 chunk 以获取 content_blocks
                text_chunks = list(stream_result.text)
            except Exception as e:
                logger.error("Model call failed: %s", e)
                raise

            self._turn_count += 1

            # 累加 token 使用量
            if stream_result.usage:
                self._total_tokens += stream_result.usage.get("input_tokens", 0)
                logger.debug("Token count: %d (+%d input)", self._total_tokens, stream_result.usage.get("input_tokens", 0))

            # 检查是否需要压缩
            self._check_compaction()

            # 用适配器解析 content blocks（处理模型差异）
            content_blocks = stream_result.content_blocks
            parsed = self._adapter.parse_response(content_blocks)

            # 没有工具调用 → 最终回复
            if not parsed.tool_calls:
                self._messages.append({
                    "role": "assistant",
                    "content": content_blocks,
                })
                return parsed.text

            # 有工具调用 → 检查工具调用次数限制
            if self._tool_call_count + len(parsed.tool_calls) > self._config.max_tool_calls:
                logger.warning(
                    "Max tool calls (%d) would be exceeded",
                    self._config.max_tool_calls,
                )
                return f"[错误] 超过最大工具调用次数限制 ({self._config.max_tool_calls})"

            # 构建 assistant 消息（含 tool_use）
            self._messages.append({
                "role": "assistant",
                "content": content_blocks,
            })

            # 执行工具（转换适配器的 ToolCall 为内部的 ToolCall）
            internal_tool_calls = [
                ToolCall(id=tc.id, name=tc.name, arguments=tc.arguments)
                for tc in parsed.tool_calls
            ]
            tool_results = self._execute_tool_calls(internal_tool_calls)

            # 注入工具结果到消息历史
            self._handle_tool_results(internal_tool_calls, tool_results)

            # 继续循环（模型会基于工具结果回复）

        # 超过最大轮次
        logger.warning("Max turns (%d) exceeded", self._config.max_turns)
        return f"[错误] 超过最大轮次限制 ({self._config.max_turns})"

    def run_stream(self, user_input: str) -> Iterator[str]:
        """运行一轮对话，流式返回文本

        与 run() 类似，但文本部分流式输出。
        工具调用时仍然阻塞等待执行完成。

        Yields:
            文本 chunk

        Raises:
            KeyboardInterrupt: 用户中断（Ctrl+C）
        """
        # 添加用户消息
        self._messages.append({"role": "user", "content": user_input})

        while self._turn_count < self._config.max_turns:
            # 检查中断
            if self._abort_controller.is_aborted:
                raise KeyboardInterrupt("Agent loop aborted")

            # 流式调用模型
            system = self._build_system_prompt()
            logger.info("Turn %d: streaming model call", self._turn_count + 1)

            try:
                stream_result = self._client.chat_stream(
                    self._messages, system=system
                )
            except Exception as e:
                logger.error("Model stream call failed: %s", e)
                raise

            # 流式输出文本 chunk
            for chunk in stream_result.text:
                yield chunk

            self._turn_count += 1

            # 累加 token 使用量
            if stream_result.usage:
                self._total_tokens += stream_result.usage.get("input_tokens", 0)
                logger.debug("Token count: %d (+%d input)", self._total_tokens, stream_result.usage.get("input_tokens", 0))

            # 检查是否需要压缩
            self._check_compaction()

            # 用适配器解析 content blocks（处理模型差异）
            content_blocks = stream_result.content_blocks
            parsed = self._adapter.parse_response(content_blocks)

            # 没有工具调用 → 最终回复
            if not parsed.tool_calls:
                self._messages.append({
                    "role": "assistant",
                    "content": content_blocks,
                })
                return

            # 有工具调用 → 检查工具调用次数限制
            if self._tool_call_count + len(parsed.tool_calls) > self._config.max_tool_calls:
                logger.warning(
                    "Max tool calls (%d) would be exceeded",
                    self._config.max_tool_calls,
                )
                yield f"\n[错误] 超过最大工具调用次数限制 ({self._config.max_tool_calls})"
                return

            # 构建 assistant 消息（含 tool_use）
            self._messages.append({
                "role": "assistant",
                "content": content_blocks,
            })

            # 执行工具（转换适配器的 ToolCall 为内部的 ToolCall）
            internal_tool_calls = [
                ToolCall(id=tc.id, name=tc.name, arguments=tc.arguments)
                for tc in parsed.tool_calls
            ]
            tool_results = self._execute_tool_calls(internal_tool_calls)

            # 注入工具结果到消息历史
            self._handle_tool_results(internal_tool_calls, tool_results)

            # 继续循环（模型会基于工具结果回复）

        # 超过最大轮次
        logger.warning("Max turns (%d) exceeded", self._config.max_turns)
        yield f"\n[错误] 超过最大轮次限制 ({self._config.max_turns})"

    def reset(self) -> None:
        """重置对话历史

        开始新的对话时调用。
        """
        self._messages.clear()
        self._turn_count = 0
        self._tool_call_count = 0
        self._total_tokens = 0
        self._abort_controller = AbortController()
        self._file_read_state = FileReadState()
        self._memory.clear_session()
        logger.info("Agent loop reset")

    @property
    def messages(self) -> list[dict[str, Any]]:
        """获取当前消息历史（只读）"""
        return self._messages.copy()

    @property
    def turn_count(self) -> int:
        """当前轮次"""
        return self._turn_count

    @property
    def tool_call_count(self) -> int:
        """当前工具调用次数"""
        return self._tool_call_count

    @property
    def token_count(self) -> int:
        """当前累计的 token 数量"""
        return self._total_tokens

    def compact(self) -> None:
        """手动触发上下文压缩

        压缩旧消息历史，保留最近的消息。
        压缩后 token 计数器重置。
        """
        if not self._messages:
            logger.info("Compact: no messages to compress")
            return

        keep_tokens = int(self._config.context_window * 0.3)
        before_count = len(self._messages)
        self._messages = self._compressor.compress(self._messages, keep_tokens)
        after_count = len(self._messages)

        # 重置 token 计数器（压缩后的消息量难以精确计算）
        self._total_tokens = 0

        logger.info("Compact: %d messages -> %d messages", before_count, after_count)
        self._notify(f"[压缩] 消息历史已压缩: {before_count} -> {after_count} 条")

    def abort(self) -> None:
        """中断当前执行"""
        self._abort_controller.abort()
        logger.info("Agent loop abort requested")

    @property
    def memory(self) -> MemoryManager:
        """获取记忆管理器"""
        return self._memory

    # ============================================================
    # 内部方法
    # ============================================================

    def _check_compaction(self) -> None:
        """检查是否需要自动压缩

        当 _total_tokens >= context_window * 0.8 时自动触发压缩。
        """
        threshold = int(self._config.context_window * 0.8)
        if self._total_tokens >= threshold:
            logger.info("Token count (%d) reached threshold (%d), auto-compacting", self._total_tokens, threshold)
            self.compact()

    def _notify(self, message: str) -> None:
        """显示通知信息

        Args:
            message: 通知内容
        """
        logger.info("Notify: %s", message)
        # 如果设置了回调，调用回调通知用户
        if self._config.on_notify:
            self._config.on_notify(message)

    def _build_system_prompt(self) -> str:
        """构建系统提示

        组合:
        1. config.system_prompt（基础提示）
        2. config.append_system_prompt（追加提示）
        3. 记忆渲染（工作记忆 + 文件摘要 + 事件笔记）
        4. 工具使用说明（动态生成）
        """
        parts = []

        if self._config.system_prompt:
            parts.append(self._config.system_prompt)

        if self._config.append_system_prompt:
            parts.append(self._config.append_system_prompt)

        # 添加记忆信息
        memory_output = self._memory.render()
        if memory_output:
            parts.append(memory_output)

        # 添加工具说明
        tools = self._registry.get_enabled_tools()
        if tools:
            tool_desc = "可用工具:\n"
            for tool in tools:
                tool_desc += f"- {tool.name}: {tool.description}\n"
            parts.append(tool_desc)

        return "\n\n".join(parts)

    def _parse_content_blocks(
        self, blocks: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        """解析 content blocks，提取文本和工具调用

        Args:
            blocks: Anthropic API 的 content blocks

        Returns:
            (文本内容, 工具调用列表)
        """
        text_parts = []
        tool_calls = []

        for block in blocks:
            block_type = block.get("type")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block["id"],
                    name=block["name"],
                    arguments=block.get("input", {}),
                ))

        text = "".join(text_parts)
        return text, tool_calls

    def _execute_tool_calls(
        self, tool_calls: list[ToolCall]
    ) -> list[ToolResult]:
        """执行多个工具调用

        Args:
            tool_calls: 工具调用列表

        Returns:
            工具执行结果列表（与 tool_calls 一一对应）
        """
        context = ToolUseContext(
            model=self._config.model,
            tools=self._registry.get_all(),
            abort_controller=self._abort_controller,
            file_read_state=self._file_read_state,
            messages=[],  # TODO: 传入消息历史
            debug=self._config.debug,
            verbose=self._config.verbose,
        )

        results = []
        for tool_call in tool_calls:
            # 检查中断
            if self._abort_controller.is_aborted:
                results.append(ToolResult(
                    output="工具执行被取消",
                    is_error=True,
                ))
                continue

            logger.info("Executing tool: %s", tool_call.name)
            result = self._registry.validate_and_execute(
                name=tool_call.name,
                arguments=tool_call.arguments,
                context=context,
            )
            results.append(result)
            self._tool_call_count += 1

        return results

    def _handle_tool_results(
        self,
        tool_calls: list[ToolCall],
        results: list[ToolResult],
    ) -> None:
        """将工具执行结果注入消息历史

        Anthropic API 格式:
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "xxx", "content": "..."},
                ...
            ]
        }

        Args:
            tool_calls: 工具调用列表
            results: 工具执行结果列表
        """
        tool_result_blocks = []
        for tool_call, result in zip(tool_calls, results):
            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": tool_call.id,
                "content": str(result.output),
            }
            if result.is_error:
                block["is_error"] = True
            tool_result_blocks.append(block)

        self._messages.append({
            "role": "user",
            "content": tool_result_blocks,
        })
