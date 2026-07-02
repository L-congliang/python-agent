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
from pathlib import Path
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
from agent.robustness.task_state import TaskState, TaskStatus, StopReason
from agent.robustness.repeat_detector import RepeatDetector
from agent.robustness.path_guard import PathGuard
from agent.robustness.retry_limiter import RetryLimiter
from agent.observability.trace import TraceEmitter
from agent.observability.reporter import RunReporter
from agent.observability.checkpoint import CheckpointManager
from agent.observability.workspace import WorkspaceSnapshot
from agent.persistence.run_store import RunStore
from agent.orchestration.sub_agent import SubAgentConstraints, SubAgentResult, SubAgentStatus
from agent.orchestration.agent_type import AgentTypeDefinition

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

    # 鲁棒性配置
    max_repeated_calls: int = 3  # 重复调用拦截阈值
    max_consecutive_failures: int = 5  # 重试上限
    workspace_root: str | None = None  # 工作区根目录

    # 可观测性配置
    enable_trace: bool = True  # 是否启用 trace
    enable_checkpoint: bool = True  # 是否启用 checkpoint
    checkpoint_interval: int = 1  # 每 N 个工具调用创建 checkpoint

    # 多 Agent 配置
    enable_subagent: bool = True  # 是否启用 SubAgentTool


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

        # 注册 SubAgentTool（如果配置允许）
        if self._config.enable_subagent:
            self._register_subagent_tool()

        # 鲁棒性组件
        self._task_state = TaskState()
        self._repeat_detector = RepeatDetector(max_repeats=self._config.max_repeated_calls)
        self._path_guard = PathGuard(workspace_root=self._config.workspace_root)
        self._retry_limiter = RetryLimiter(max_retries=self._config.max_consecutive_failures)

        # 可观测性组件
        self._run_store = RunStore(Path(".agent/runs"))
        self._run_dir: Path | None = None
        self._trace: TraceEmitter | None = None
        self._reporter: RunReporter | None = None
        self._checkpoint_mgr: CheckpointManager | None = None
        self._workspace_snapshot: WorkspaceSnapshot | None = None

        if self._config.enable_trace:
            self._run_dir = self._run_store.create_run_dir()
            self._trace = TraceEmitter(self._run_dir)
            self._reporter = RunReporter(self._run_dir, self._trace.run_id)

        if self._config.enable_checkpoint:
            checkpoint_dir = Path(".agent/checkpoints")
            self._checkpoint_mgr = CheckpointManager(checkpoint_dir)

        if self._config.workspace_root:
            self._workspace_snapshot = WorkspaceSnapshot(Path(self._config.workspace_root))

        # 子 Agent 约束（只有子 Agent 才有）
        self._subagent_constraints: SubAgentConstraints | None = None

    # ============================================================
    # 子 Agent 工厂方法
    # ============================================================

    @classmethod
    def create_sub_agent(
        cls,
        parent: AgentLoop,
        task: str,
        agent_type_def: AgentTypeDefinition,
        constraints: SubAgentConstraints,
        extra_context: str = "",
    ) -> AgentLoop:
        """工厂方法：从父 Agent 创建子 Agent

        对齐 Claude Code 的子 Agent 创建逻辑：
        - 继承 client 和 adapter
        - 继承父 Agent 的记忆（通过 system prompt）
        - 使用 agent_type 定义的工具集
        - 共享约束（token budget、abort、counter）

        Args:
            parent: 父 AgentLoop 实例
            task: 子 Agent 的任务描述
            agent_type_def: Agent 类型定义
            constraints: 共享约束
            extra_context: 额外上下文（可选）

        Returns:
            新的 AgentLoop 实例（子 Agent）
        """
        # 1. 构建子 Agent 的 system prompt
        system_prompt = cls._build_subagent_prompt(
            parent=parent,
            agent_type_def=agent_type_def,
            task=task,
            extra_context=extra_context,
        )

        # 2. 创建受限的 ToolRegistry
        sub_registry = cls._filter_registry(
            parent._registry,
            agent_type_def.allowed_tools,
        )

        # 3. 确定 max_turns（取类型默认值和父 Agent 剩余轮次的较小值）
        parent_remaining_turns = parent._config.max_turns - parent._turn_count
        type_default_turns = agent_type_def.default_max_turns or 20
        max_turns = min(type_default_turns, parent_remaining_turns)

        # 4. 创建子 Agent 的 LoopConfig
        sub_config = LoopConfig(
            model=agent_type_def.default_model or parent._config.model,
            max_turns=max_turns,
            max_tool_calls=50,
            system_prompt=system_prompt,
            enable_trace=False,  # 嵌套到父 Agent 的 trace
            enable_checkpoint=False,
            workspace_root=parent._config.workspace_root,
        )

        # 5. 创建子 AgentLoop
        sub_agent = cls(
            client=parent._client,
            registry=sub_registry,
            config=sub_config,
            adapter=parent._adapter,
        )
        sub_agent._subagent_constraints = constraints

        # 6. 记录 agent 创建
        constraints.record_agent_created()

        logger.info(
            "Created sub-agent: type=%s, max_turns=%d, tools=%s",
            agent_type_def.name,
            max_turns,
            [t.name for t in sub_registry.get_all()],
        )

        return sub_agent

    @staticmethod
    def _build_subagent_prompt(
        parent: AgentLoop,
        agent_type_def: AgentTypeDefinition,
        task: str,
        extra_context: str = "",
    ) -> str:
        """构建子 Agent 的 system prompt

        组合：
        1. agent_type 的 system_prompt（如果有）
        2. 父 Agent 的 memory.render_compact() 输出
        3. 额外上下文（如果有）
        4. 工具列表

        Args:
            parent: 父 AgentLoop 实例
            agent_type_def: Agent 类型定义
            task: 子 Agent 的任务描述
            extra_context: 额外上下文

        Returns:
            组合后的 system prompt
        """
        parts = []

        # Agent 类型的 system prompt
        if agent_type_def.system_prompt:
            parts.append(agent_type_def.system_prompt)
        else:
            parts.append(
                f"You are a sub-agent of type '{agent_type_def.name}'. "
                f"{agent_type_def.description}"
            )

        # 父 Agent 的记忆（只读继承）
        parent_memory = parent._memory.render_compact()
        if parent_memory:
            parts.append(f"Parent agent context:\n{parent_memory}")

        # 额外上下文
        if extra_context:
            parts.append(extra_context)

        # 工具列表
        tools = parent._registry.get_enabled_tools()
        if agent_type_def.allowed_tools:
            tools = [t for t in tools if t.name in agent_type_def.allowed_tools]
        if tools:
            tool_desc = "Available tools:\n"
            for tool in tools:
                tool_desc += f"- {tool.name}: {tool.description}\n"
            parts.append(tool_desc)

        return "\n\n".join(parts)

    @staticmethod
    def _filter_registry(
        registry: ToolRegistry,
        allowed_tools: list[str] | None,
    ) -> ToolRegistry:
        """从父 Agent 的 registry 过滤出允许的工具

        Args:
            registry: 父 Agent 的 ToolRegistry
            allowed_tools: 允许的工具名列表（None = 全部）

        Returns:
            过滤后的新 ToolRegistry
        """
        if allowed_tools is None:
            return registry.clone()
        return registry.filter_by_names(allowed_tools)

    def create_subagent_result(self, final_answer: str = "") -> SubAgentResult:
        """创建子 Agent 的执行结果

        Args:
            final_answer: 最终回复文本

        Returns:
            SubAgentResult 实例
        """
        # 确定状态
        if self._task_state.status == TaskStatus.COMPLETED:
            status = SubAgentStatus.COMPLETED
        elif self._task_state.status == TaskStatus.STOPPED:
            status = SubAgentStatus.STOPPED
        elif self._task_state.status == TaskStatus.FAILED:
            status = SubAgentStatus.FAILED
        else:
            status = SubAgentStatus.COMPLETED

        return SubAgentResult(
            result=final_answer,
            status=status,
            turns_used=self._turn_count,
            tool_calls_used=self._tool_call_count,
            tokens_used=self._total_tokens,
            agent_type=getattr(self, '_agent_type_name', 'general-purpose'),
            error=self._task_state.metadata.get("error"),
        )

    def run(self, user_input: str) -> str:
        """运行一轮完整的对话（同步）

        流程:
        1. 构建消息（历史 + 用户输入）
        2. 调用模型（内部用 chat_stream 获取 content_blocks）
        3. 解析响应（文本 + tool_use）
        4. 如果有 tool_use → 执行工具 → 注入结果 → 回到步骤 2
        5. 如果没有 tool_use → 返回模型回复

        鲁棒性:
        - 错误恢复：模型调用失败时注入错误信息，让模型决定重试或换工具
        - 重复调用拦截：检测并阻止连续相同调用
        - 路径逃逸防护：文件路径必须在工作区内
        - 重试上限：连续无效调用强制停止

        Args:
            user_input: 用户输入的文本

        Returns:
            模型的最终回复文本

        Raises:
            KeyboardInterrupt: 用户中断（Ctrl+C）
        """
        # 子 Agent 约束检查
        if self._subagent_constraints:
            if not self._subagent_constraints.can_create_agent():
                return "[错误] 超过最大 Agent 数量限制"
            if self._subagent_constraints.remaining_budget() <= 0:
                return "[错误] Token 预算已耗尽"

        # 初始化任务状态
        self._task_state = TaskState(user_request=user_input)
        self._repeat_detector.reset()
        self._retry_limiter.reset()

        # 重新打开 trace（如果已关闭）
        if self._config.enable_trace and self._trace and self._trace._file.closed:
            self._run_dir = self._run_store.create_run_dir()
            self._trace = TraceEmitter(self._run_dir)
            self._reporter = RunReporter(self._run_dir, self._trace.run_id)

        # 发射 run_started 事件
        if self._trace:
            self._trace.emit("run_started", {
                "user_request": user_input,
                "config": {
                    "model": self._config.model,
                    "max_turns": self._config.max_turns,
                    "max_tool_calls": self._config.max_tool_calls,
                    "context_window": self._config.context_window,
                },
            })
            self._reporter.record_start(user_request=user_input)

        # 捕获工作区快照
        if self._workspace_snapshot:
            workspace_info = self._workspace_snapshot.capture()
            if self._trace:
                self._trace.emit("workspace_snapshot", workspace_info)

        # 添加用户消息
        self._messages.append({"role": "user", "content": user_input})

        while self._turn_count < self._config.max_turns:
            # 检查中断
            if self._abort_controller.is_aborted:
                self._task_state.stop(StopReason.USER_ABORT)
                raise KeyboardInterrupt("Agent loop aborted")

            # 检查任务状态
            if self._task_state.is_done:
                break

            # 调用模型（内部用 chat_stream 获取 content_blocks）
            system = self._build_system_prompt()
            logger.info("Turn %d: calling model", self._turn_count + 1)

            # 发射 model_requested 事件
            if self._trace:
                self._trace.emit("model_requested", {
                    "turn": self._turn_count + 1,
                    "messages_count": len(self._messages),
                    "system_prompt_tokens": len(system) // 4,  # 粗略估算
                })

            try:
                stream_result = self._client.chat_stream(
                    self._messages, system=system
                )
                # 消费所有 chunk 以获取 content_blocks
                text_chunks = list(stream_result.text)
            except Exception as e:
                # 模型错误：设置任务状态为 FAILED
                logger.error("Model call failed: %s", e)
                if self._trace:
                    self._trace.emit("error", {
                        "type": "model_error",
                        "exception": type(e).__name__,
                        "message": str(e),
                    })
                self._task_state.fail(StopReason.MODEL_ERROR, str(e))
                raise

            self._turn_count += 1
            if self._reporter:
                self._reporter.record_turn()

            # 累加 token 使用量
            if stream_result.usage:
                input_tokens = stream_result.usage.get("input_tokens", 0)
                output_tokens = stream_result.usage.get("output_tokens", 0)
                self._total_tokens += input_tokens
                logger.debug("Token count: %d (+%d input)", self._total_tokens, input_tokens)
                if self._reporter:
                    self._reporter.record_tokens(input_tokens, output_tokens)
                # 子 Agent 约束追踪
                if self._subagent_constraints:
                    self._subagent_constraints.record_tokens_spent(input_tokens + output_tokens)

            # 检查是否需要压缩
            self._check_compaction()

            # 用适配器解析 content blocks（处理模型差异）
            content_blocks = stream_result.content_blocks
            parsed = self._adapter.parse_response(content_blocks)

            # 发射 model_responded 事件
            if self._trace:
                self._trace.emit("model_responded", {
                    "turn": self._turn_count,
                    "usage": stream_result.usage or {},
                    "tool_calls_count": len(parsed.tool_calls),
                    "text_preview": parsed.text[:100] if parsed.text else None,
                })

            # 没有工具调用 → 最终回复
            if not parsed.tool_calls:
                self._messages.append({
                    "role": "assistant",
                    "content": content_blocks,
                })
                self._task_state.complete(parsed.text)

                # 发射 run_finished 事件
                if self._trace:
                    self._trace.emit("run_finished", {
                        "status": "completed",
                        "stop_reason": "normal",
                        "total_turns": self._turn_count,
                        "total_tool_calls": self._tool_call_count,
                        "total_tokens_used": self._total_tokens,
                        "final_answer_preview": parsed.text[:200] if parsed.text else None,
                    })
                    self._trace.close()
                if self._reporter:
                    self._reporter.record_finish(
                        status="completed",
                        final_answer=parsed.text,
                        stop_reason="normal",
                    )

                return parsed.text

            # 有工具调用 → 检查工具调用次数限制
            if self._tool_call_count + len(parsed.tool_calls) > self._config.max_tool_calls:
                logger.warning(
                    "Max tool calls (%d) would be exceeded",
                    self._config.max_tool_calls,
                )
                self._task_state.stop(StopReason.STEP_LIMIT)
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
        self._task_state.stop(StopReason.STEP_LIMIT)

        # 发射 run_finished 事件
        if self._trace:
            self._trace.emit("run_finished", {
                "status": "stopped",
                "stop_reason": "max_turns_exceeded",
                "total_turns": self._turn_count,
                "total_tool_calls": self._tool_call_count,
                "total_tokens_used": self._total_tokens,
            })
            self._trace.close()
        if self._reporter:
            self._reporter.record_finish(
                status="stopped",
                stop_reason="max_turns_exceeded",
            )

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
        # 初始化任务状态
        self._task_state = TaskState(user_request=user_input)
        self._repeat_detector.reset()
        self._retry_limiter.reset()

        # 添加用户消息
        self._messages.append({"role": "user", "content": user_input})

        while self._turn_count < self._config.max_turns:
            # 检查中断
            if self._abort_controller.is_aborted:
                self._task_state.stop(StopReason.USER_ABORT)
                raise KeyboardInterrupt("Agent loop aborted")

            # 检查任务状态
            if self._task_state.is_done:
                break

            # 流式调用模型
            system = self._build_system_prompt()
            logger.info("Turn %d: streaming model call", self._turn_count + 1)

            try:
                stream_result = self._client.chat_stream(
                    self._messages, system=system
                )
            except Exception as e:
                # 模型错误：设置任务状态为 FAILED
                logger.error("Model stream call failed: %s", e)
                self._task_state.fail(StopReason.MODEL_ERROR, str(e))
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
                self._task_state.complete(parsed.text)
                return

            # 有工具调用 → 检查工具调用次数限制
            if self._tool_call_count + len(parsed.tool_calls) > self._config.max_tool_calls:
                logger.warning(
                    "Max tool calls (%d) would be exceeded",
                    self._config.max_tool_calls,
                )
                self._task_state.stop(StopReason.STEP_LIMIT)
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

            # 检查重试上限
            if self._task_state.is_done:
                break

            # 继续循环（模型会基于工具结果回复）

        # 超过最大轮次
        if self._task_state.is_running:
            logger.warning("Max turns (%d) exceeded", self._config.max_turns)
            self._task_state.stop(StopReason.STEP_LIMIT)
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
        # 重置鲁棒性组件
        self._task_state = TaskState()
        self._repeat_detector.reset()
        self._retry_limiter.reset()
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

    @property
    def task_state(self) -> TaskState:
        """获取任务状态"""
        return self._task_state

    @property
    def path_guard(self) -> PathGuard:
        """获取路径防护器"""
        return self._path_guard

    # ============================================================
    # 内部方法
    # ============================================================

    def _register_subagent_tool(self) -> None:
        """注册 SubAgentTool 到 ToolRegistry

        如果 SubAgentTool 未注册，则注册它。
        """
        if self._registry.get("subagent") is None:
            from agent.tools.subagent import SubAgentTool
            self._registry.register(SubAgentTool)
            logger.debug("Registered SubAgentTool")

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

        # 添加 SubAgent 使用说明（如果已注册）
        if self._registry.get("subagent") is not None:
            parts.append(
                "## SubAgent 使用指南\n"
                "当任务可以并行执行、需要独立上下文、或涉及大量文件搜索时，"
                "使用 subagent 工具派生子 Agent。\n"
                "适用场景：\n"
                "- 搜索大量文件（如搜索所有 TODO）\n"
                "- 复杂多步任务（可以拆分为独立子任务）\n"
                "- 需要独立上下文的任务（避免污染主对话）\n"
                "不适用场景：\n"
                "- 简单单步操作（直接用现有工具更快）\n"
                "- 需要用户交互的任务（子 Agent 不能向用户提问）"
            )

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
        """执行多个工具调用（带鲁棒性检查）

        鲁棒性检查顺序:
        1. 重复调用检测 → 拦截连续相同调用
        2. 路径逃逸防护 → 文件路径必须在工作区内
        3. 重试上限 → 连续无效调用强制停止

        Args:
            tool_calls: 工具调用列表

        Returns:
            工具执行结果列表（与 tool_calls 一一对应）
        """
        import time

        context = ToolUseContext(
            model=self._config.model,
            tools=self._registry.get_all(),
            abort_controller=self._abort_controller,
            file_read_state=self._file_read_state,
            messages=self._messages,
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

            # 检查重复调用
            is_repeated, repeat_msg = self._repeat_detector.check(
                tool_call.name, tool_call.arguments
            )
            if is_repeated:
                logger.warning("Repeated call detected: %s - %s", tool_call.name, repeat_msg)
                results.append(ToolResult(output=repeat_msg, is_error=True))
                self._retry_limiter.record_failure()
                continue

            # 检查路径逃逸（仅文件相关工具）
            if tool_call.name in ("read", "write", "edit"):
                file_path = tool_call.arguments.get("file_path") or tool_call.arguments.get("path", "")
                if file_path:
                    is_safe, path_msg = self._path_guard.check_path(file_path)
                    if not is_safe:
                        logger.warning("Path escape detected: %s", path_msg)
                        results.append(ToolResult(output=path_msg, is_error=True))
                        self._retry_limiter.record_failure()
                        continue

            # 执行工具
            logger.info("Executing tool: %s", tool_call.name)
            start_time = time.time()
            result = self._registry.validate_and_execute(
                name=tool_call.name,
                arguments=tool_call.arguments,
                context=context,
            )
            duration_ms = int((time.time() - start_time) * 1000)
            results.append(result)
            self._tool_call_count += 1
            self._task_state.increment_tool_steps()

            # 发射 tool_executed 事件
            if self._trace:
                self._trace.emit("tool_executed", {
                    "turn": self._turn_count,
                    "tool_name": tool_call.name,
                    "tool_id": tool_call.id,
                    "input": tool_call.arguments,
                    "output_preview": str(result.output)[:200] if result.output else None,
                    "duration_ms": duration_ms,
                    "is_error": result.is_error,
                })

            # 记录到 reporter
            if self._reporter:
                self._reporter.record_tool_call(
                    tool_name=tool_call.name,
                    tool_args=tool_call.arguments,
                    duration_ms=duration_ms,
                    is_error=result.is_error,
                )

            # 追踪文件（用于 checkpoint）
            if self._checkpoint_mgr and tool_call.name in ("read", "write", "edit"):
                file_path = tool_call.arguments.get("file_path") or tool_call.arguments.get("path", "")
                if file_path:
                    self._checkpoint_mgr.track_file(file_path, tool_call.name)

            # 创建 checkpoint
            if self._checkpoint_mgr and self._tool_call_count % self._config.checkpoint_interval == 0:
                checkpoint = self._checkpoint_mgr.create(
                    goal=self._task_state.user_request or "",
                    completed_steps=[f"已执行 {self._task_state.tool_steps} 个工具调用"],
                    next_step="继续执行",
                    run_id=self._trace.run_id if self._trace else None,
                    messages=self._messages.copy(),
                )
                if self._trace:
                    self._trace.emit("checkpoint_created", {
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "goal": checkpoint.goal,
                        "tracked_files_count": len(checkpoint.tracked_files),
                    })

            # 记录重试状态
            if result.is_error:
                self._retry_limiter.record_failure()
            else:
                self._retry_limiter.record_success()

            # 检查重试上限
            if self._retry_limiter.is_exceeded:
                logger.warning("Retry limit exceeded, stopping")
                self._task_state.stop(StopReason.RETRY_LIMIT)
                break

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
