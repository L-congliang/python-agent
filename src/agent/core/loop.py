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
    ObservationMetadata,
    PermissionBehavior,
    PermissionConfirmationOutcome,
    PermissionRequest,
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
from agent.permissions.checker import PermissionChecker, PermissionMode

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

    # Plan Mode
    plan_mode: bool = False  # 是否处于计划模式

    # 回调
    on_notify: Callable[[str], None] | None = None  # 通知回调
    permission_handler: Callable[[PermissionRequest], PermissionConfirmationOutcome] | None = None
    on_tool_result: Callable[[ToolCall, ToolResult], None] | None = None  # 工具执行完成回调

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

    # Observation Budget：artifact 保存目录
    artifact_dir: str | None = None  # None 表示不保存 artifact

    # Edit History：编辑历史目录
    edit_history_dir: str | None = None  # None 表示不记录历史

    # Session 持久化
    session_dir: str | None = None  # None 表示不持久化 session
    enable_autosave: bool = True  # 是否启用自动保存

    # 多 Agent 配置
    enable_subagent: bool = True  # 是否启用 SubAgentTool

    # 记忆系统配置
    memory_enabled: bool = True  # 是否启用记忆系统（用于 memory_on/off 对照实验）

    # Session Policy 配置
    enable_session_policy: bool = True  # 是否启用 session 级权限策略


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
        # 工具执行历史（用于评测统计）
        self._tool_history: list[dict[str, Any]] = []
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

        # 权限检查器
        initial_mode = PermissionMode.PLAN if self._config.plan_mode else PermissionMode.DEFAULT
        self._permission_checker = PermissionChecker(mode=initial_mode)

        # 可观测性组件
        self._run_store = RunStore(Path(".agent/runs"))
        self._run_dir: Path | None = None
        self._trace: TraceEmitter | None = None
        self._reporter: RunReporter | None = None

        # Edit History 存储（延迟导入，避免循环依赖）
        self._edit_history_store: Any = None
        if self._config.edit_history_dir:
            from agent.persistence.edit_history_store import EditHistoryStore
            self._edit_history_store = EditHistoryStore(self._config.edit_history_dir)

        # Session 持久化（延迟导入，避免循环依赖）
        self._session_store: Any = None
        self._session_id: str | None = None
        if self._config.session_dir:
            from agent.persistence.session_store import SessionStore
            self._session_store = SessionStore(Path(self._config.session_dir))

        # Resume freshness 状态
        self._resume_freshness_summary: dict[str, Any] | None = None

        # Session Policy（延迟导入，避免循环依赖）
        self._session_policy: Any = None
        if self._config.enable_session_policy:
            from agent.permissions.session_policy import SessionPermissionPolicy
            self._session_policy = SessionPermissionPolicy()
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

    def set_permission_handler(
        self,
        handler: Callable[[PermissionRequest], PermissionConfirmationOutcome] | None,
    ) -> None:
        """注入权限确认处理器。"""
        self._config.permission_handler = handler

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
            memory_enabled=parent._config.memory_enabled,
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

        # 父 Agent 的记忆（只读继承，受 memory_enabled 开关控制）
        parent_memory = parent._memory.render_compact() if parent._config.memory_enabled else ""
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

        # 记忆：记录当前任务
        if self._config.memory_enabled:
            self._memory.set_task(user_input)

        try:
            return self._run_inner(user_input)
        finally:
            # 记忆：持久化（确保 durable memory 不丢失）
            if self._config.memory_enabled:
                self._memory.save()

    def _run_inner(self, user_input: str) -> str:
        """run() 的内部实现（被 try/finally 包裹）

        Args:
            user_input: 用户输入

        Returns:
            模型最终回复
        """
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

        self._update_plan_mode_from_input(user_input)

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
                # 获取工具列表（Anthropic 格式）
                tools = self._registry.to_anthropic_tools()
                stream_result = self._client.chat_stream(
                    self._messages, system=system, tools=tools if tools else None
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

        # 记忆：记录当前任务
        if self._config.memory_enabled:
            self._memory.set_task(user_input)

        try:
            self._update_plan_mode_from_input(user_input)

            # 添加用户消息
            self._messages.append({"role": "user", "content": user_input})

            yield from self._run_stream_inner(user_input)
        finally:
            # 记忆：持久化（确保 durable memory 不丢失）
            if self._config.memory_enabled:
                self._memory.save()

    def _run_stream_inner(self, user_input: str) -> Iterator[str]:
        """run_stream() 的内部实现（被 try/finally 包裹）

        Yields:
            文本 chunk
        """
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
                # 获取工具列表（Anthropic 格式）
                tools = self._registry.to_anthropic_tools()
                stream_result = self._client.chat_stream(
                    self._messages, system=system, tools=tools if tools else None
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
        self._tool_history.clear()
        self._memory.clear_session()
        # 重置鲁棒性组件
        self._task_state = TaskState()
        self._repeat_detector.reset()
        self._retry_limiter.reset()
        # 清空 session policy
        if self._session_policy is not None:
            self._session_policy.clear()
        # 重置 session_id，下次 save_session 时生成新 session
        self._session_id = None
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

    def compact(self) -> tuple[int, int]:
        """手动触发上下文压缩

        压缩旧消息历史，保留最近的消息。
        压缩后 token 计数器重置。
        """
        if not self._messages:
            logger.info("Compact: no messages to compress")
            return (0, 0)

        keep_tokens = int(self._config.context_window * 0.3)
        before_count = len(self._messages)
        self._messages = self._compressor.compress(self._messages, keep_tokens)
        after_count = len(self._messages)

        # 重置 token 计数器（压缩后的消息量难以精确计算）
        self._total_tokens = 0

        logger.info("Compact: %d messages -> %d messages", before_count, after_count)
        self._notify(f"[压缩] 消息历史已压缩: {before_count} -> {after_count} 条")
        return (before_count, after_count)

    def abort(self) -> None:
        """中断当前执行"""
        self._abort_controller.abort()
        logger.info("Agent loop abort requested")

    def enable_plan_mode(self) -> None:
        """启用 Plan Mode

        切换权限检查器到 PLAN 模式，禁止所有写操作。
        """
        self._config.plan_mode = True
        self._permission_checker.set_mode(PermissionMode.PLAN)
        logger.info("Plan mode enabled")

    def disable_plan_mode(self) -> None:
        """禁用 Plan Mode

        切换权限检查器到 DEFAULT 模式，恢复正常权限。
        """
        self._config.plan_mode = False
        self._permission_checker.set_mode(PermissionMode.DEFAULT)
        logger.info("Plan mode disabled")

    @property
    def memory(self) -> MemoryManager:
        """获取记忆管理器"""
        return self._memory

    @property
    def tool_history(self) -> list[dict[str, Any]]:
        """获取工具执行历史（只读）"""
        return self._tool_history.copy()

    def clear_tool_history(self) -> None:
        """清空工具执行历史（用于实验隔离 setup_turns 和主任务）"""
        self._tool_history.clear()

    # ========== Session 持久化 ==========

    def export_session_state(self) -> dict[str, Any]:
        """导出当前 session 状态

        Returns:
            session 状态字典
        """
        return {
            "session_id": self._session_id,
            "messages": self._messages.copy(),
            "turn_count": self._turn_count,
            "tool_call_count": self._tool_call_count,
            "total_tokens": self._total_tokens,
            "memory": self._memory.export_state() if hasattr(self._memory, 'export_state') else {},
            "workspace_root": self._config.workspace_root,
            "last_run_id": self._run_dir.name if self._run_dir else None,
        }

    def import_session_state(self, state: dict[str, Any]) -> None:
        """导入 session 状态

        Args:
            state: session 状态字典
        """
        # 兼容两种字段名：session_id（export 导出）和 id（SessionStore 存储）
        self._session_id = state.get("session_id") or state.get("id")
        self._messages = state.get("messages", [])
        self._turn_count = state.get("turn_count", 0)
        self._tool_call_count = state.get("tool_call_count", 0)
        self._total_tokens = state.get("total_tokens", 0)

        # 恢复 memory
        memory_state = state.get("memory", {})
        if memory_state and hasattr(self._memory, 'import_state'):
            self._memory.import_state(memory_state)

        logger.info("Session state imported: session_id=%s, messages=%d",
                     self._session_id, len(self._messages))

    def save_session(self) -> str | None:
        """保存当前 session

        Returns:
            session_id，如果未启用 session store 则返回 None
        """
        if self._session_store is None or not self._config.enable_autosave:
            return None

        state = self.export_session_state()
        session_id = self._session_store.save(
            messages=state["messages"],
            memory=state["memory"],
            workspace_root=state["workspace_root"],
            session_id=self._session_id,
        )
        self._session_id = session_id
        return session_id

    @property
    def session_id(self) -> str | None:
        """当前 session ID"""
        return self._session_id

    @property
    def session_store(self) -> Any:
        """Session store"""
        return self._session_store

    # ========== 摘要接口 ==========

    def get_session_summary(self) -> dict[str, Any] | None:
        """获取当前 session 摘要

        Returns:
            session 摘要字典，没有活动 session 时返回 None
        """
        if self._session_store is None or self._session_id is None:
            return None

        data = self._session_store.load(self._session_id)
        if data is None:
            return None

        return {
            "session_id": data.get("id"),
            "created_at": data.get("created_at"),
            "workspace_root": data.get("workspace_root"),
            "message_count": len(data.get("messages", [])),
        }

    def list_recent_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        """列出最近 sessions

        Args:
            limit: 最大返回数量

        Returns:
            session 摘要列表
        """
        if self._session_store is None:
            return []

        return self._session_store.list_sessions()[:limit]

    def get_run_summary(self) -> dict[str, Any]:
        """获取当前 run 摘要

        Returns:
            run 摘要字典
        """
        return {
            "run_id": self._run_dir.name if self._run_dir else None,
            "session_id": self._session_id,
            "workspace_root": self._config.workspace_root,
            "model": self._config.model,
            "turn_count": self._turn_count,
            "tool_call_count": self._tool_call_count,
        }

    def get_workspace_summary(self) -> dict[str, Any]:
        """获取 workspace 摘要

        Returns:
            workspace 摘要字典
        """
        if self._workspace_snapshot is None:
            return {"workspace_root": self._config.workspace_root}

        info = self._workspace_snapshot.capture()
        return {
            "workspace_root": info.get("workspace_root"),
            "git_branch": info.get("git_branch"),
            "recent_commits_count": len(info.get("recent_commits", [])),
            "has_readme": "README.md" in info.get("project_docs", {}),
            "has_pyproject": "pyproject.toml" in info.get("project_docs", {}),
        }

    def get_checkpoint_summary(self) -> dict[str, Any] | None:
        """获取 checkpoint 摘要

        Returns:
            checkpoint 摘要字典，没有 checkpoint 时返回 None
        """
        if self._checkpoint_mgr is None:
            return None

        return {
            "has_checkpoint": True,
            "checkpoint_dir": str(self._checkpoint_mgr._checkpoint_dir),
        }

    def get_inspect_summary(self) -> dict[str, Any]:
        """获取 inspect 摘要（run + session + workspace + checkpoint + freshness）

        Returns:
            inspect 摘要字典
        """
        return {
            "run": self.get_run_summary(),
            "session": self.get_session_summary(),
            "workspace": self.get_workspace_summary(),
            "checkpoint": self.get_checkpoint_summary(),
            "freshness": self._resume_freshness_summary,
        }

    def set_resume_freshness_summary(self, summary: dict[str, Any] | None) -> None:
        """设置 resume freshness 摘要

        Args:
            summary: freshness 摘要字典
        """
        self._resume_freshness_summary = summary

    def get_resume_freshness_summary(self) -> dict[str, Any] | None:
        """获取 resume freshness 摘要

        Returns:
            freshness 摘要字典，没有时返回 None
        """
        return self._resume_freshness_summary

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

    def _detect_planning_intent(self, user_input: str) -> bool:
        """检测用户是否表达规划意图

        通过关键词匹配判断，不调用模型。
        匹配到规划意图时自动启用 Plan Mode。

        Args:
            user_input: 用户输入

        Returns:
            True 如果检测到规划意图
        """
        planning_keywords = [
            "先规划", "先想清楚", "先计划", "列出计划",
            "做个计划", "做个规划", "规划一下", "计划一下",
            "先想一下", "先分析一下", "先设计一下",
        ]
        input_lower = user_input.lower()
        return any(keyword in input_lower for keyword in planning_keywords)

    def _detect_confirmation_intent(self, user_input: str) -> bool:
        """检测用户是否确认计划

        Args:
            user_input: 用户输入

        Returns:
            True 如果检测到确认意图
        """
        confirm_keywords = ["确认", "执行", "开始", "同意", "可以", "好的"]
        input_lower = user_input.lower()
        return any(keyword in input_lower for keyword in confirm_keywords)

    def _detect_cancel_intent(self, user_input: str) -> bool:
        """检测用户是否取消计划

        Args:
            user_input: 用户输入

        Returns:
            True 如果检测到取消意图
        """
        cancel_keywords = ["取消", "直接改", "直接做", "不用规划了"]
        input_lower = user_input.lower()
        return any(keyword in input_lower for keyword in cancel_keywords)

    def _update_plan_mode_from_input(self, user_input: str) -> None:
        """统一处理用户输入触发的 Plan Mode 切换。"""
        if self._detect_planning_intent(user_input):
            self.enable_plan_mode()

        if self._config.plan_mode:
            if self._detect_confirmation_intent(user_input):
                self.disable_plan_mode()
            elif self._detect_cancel_intent(user_input):
                self.disable_plan_mode()

    def _check_compaction(self) -> None:
        """检查是否需要自动压缩

        当 _total_tokens >= context_window * 0.8 时自动触发压缩。
        """
        threshold = int(self._config.context_window * 0.8)
        if self._total_tokens >= threshold:
            logger.info("Token count (%d) reached threshold (%d), auto-compacting", self._total_tokens, threshold)
            self.compact()

    def _build_permission_request(
        self,
        tool_call: ToolCall,
        context: ToolUseContext,
        message: str,
    ) -> PermissionRequest:
        """构造权限确认请求。"""
        preview: str | None = None
        if tool_call.name == "edit":
            from agent.tools.file_edit import execute_file_edit

            preview_input = dict(tool_call.arguments)
            preview_input["preview"] = True
            preview_result = execute_file_edit(preview_input, context)
            if preview_result.is_error:
                preview = f"无法生成 diff 预览: {preview_result.output}"
            else:
                preview = str(preview_result.output)

        return PermissionRequest(
            tool_name=tool_call.name,
            tool_input=dict(tool_call.arguments),
            message=message,
            preview=preview,
        )

    def _build_permission_result_lines(
        self,
        request: PermissionRequest,
        *,
        header: str,
        detail: str,
    ) -> list[str]:
        """构造权限相关 observation 文本。"""
        parts = [header, detail]

        if request.tool_name == "bash":
            command = str(request.tool_input.get("command", "")).strip()
            if command:
                parts.append(f"待执行命令: {command}")
        elif request.tool_name in ("write", "edit"):
            file_path = str(request.tool_input.get("file_path", "")).strip()
            if file_path:
                parts.append(f"目标文件: {file_path}")

        if request.preview:
            parts.append(request.preview)

        return parts

    def _build_permission_ask_result(self, request: PermissionRequest) -> ToolResult:
        """没有确认能力时，ASK 保持 fail-closed。"""
        return ToolResult(
            output="\n".join(
                self._build_permission_result_lines(
                    request,
                    header=f"[需要确认] {request.message}",
                    detail="当前环境未提供交互式确认能力，因此本次工具调用未执行。",
                )
            ),
            is_error=True,
        )

    def _build_permission_rejected_result(self, request: PermissionRequest) -> ToolResult:
        """用户拒绝后的 observation。"""
        return ToolResult(
            output="\n".join(
                self._build_permission_result_lines(
                    request,
                    header=f"[用户拒绝] {request.message}",
                    detail=f"用户拒绝执行工具 '{request.tool_name}'，本次调用未执行。",
                )
            ),
            is_error=True,
        )

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
        """构建系统提示（通过 ContextManager 预算裁剪）

        V1 流程：
        1. 静态前缀（identity + behavior + tool_guide）来自 SystemPromptBuilder.build_prefix()
        2. 工具列表来自 registry
        3. 记忆通过 MemoryManager.assemble_layered() 分层组装
        4. 历史通过 format_history() 转为结构化摘要
        5. ContextManager.build_prompt() 统一预算裁剪和组装
        """
        from agent.prompts.builder import SystemPromptBuilder
        from agent.context.history_formatter import format_history

        # 1. 静态前缀
        prefix = SystemPromptBuilder.build_prefix(plan_mode=self._config.plan_mode)

        # 2. 额外 prompt（用户自定义部分）
        extra_parts: list[str] = []
        if self._config.system_prompt:
            extra_parts.append(self._config.system_prompt)
        if self._config.append_system_prompt:
            extra_parts.append(self._config.append_system_prompt)
        if extra_parts:
            prefix += "\n\n" + "\n\n".join(extra_parts)

        # 3. 工具列表
        tools = self._format_tools_text()

        # 4. 记忆（分层组装）
        memory = ""
        if self._config.memory_enabled and self._memory:
            query = self._memory.get_task() or ""
            memory_budget = self._context_manager._budget.get_section("memory")
            max_tokens = memory_budget.max_tokens if memory_budget else 1600
            memory = self._memory.assemble_layered(query, max_tokens=max_tokens)

        # 5. 当前请求（最近一条 user 消息）
        current_request = ""
        last_user_idx = -1
        for i in range(len(self._messages) - 1, -1, -1):
            if self._messages[i].get("role") == "user":
                content = self._messages[i].get("content", "")
                if isinstance(content, str):
                    current_request = content
                last_user_idx = i
                break

        # 6. 历史（结构化摘要，排除最后一条 user 消息避免重复注入）
        history_messages = self._messages[:last_user_idx] if last_user_idx > 0 else []
        history = format_history(history_messages)

        # 7. ContextManager 组装
        prompt, metadata = self._context_manager.build_prompt(
            prefix=prefix,
            tools=tools,
            memory=memory,
            history=history,
            current_request=current_request,
        )
        self._last_context_metadata = metadata

        return prompt

    def _format_tools_text(self) -> str:
        """格式化工具列表为文本"""
        tools = self._registry.get_enabled_tools()
        if not tools:
            return ""
        parts = ["可用工具:"]
        for tool in tools:
            parts.append(f"- {tool.name}: {tool.description}")
        # SubAgent 指南
        if self._registry.get("subagent") is not None:
            parts.append(
                "\n## SubAgent 使用指南\n"
                "当任务可以并行执行、需要独立上下文、或涉及大量文件搜索时，"
                "使用 subagent 工具派生子 Agent。"
            )
        return "\n".join(parts)

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
            cwd=self._config.workspace_root or ".",
            agent_loop=self,
            artifact_dir=self._config.artifact_dir,
            edit_history_store=self._edit_history_store,
        )

        results = []
        for tool_call in tool_calls:
            confirmation_note: str | None = None
            # 检查中断
            if self._abort_controller.is_aborted:
                result = ToolResult(
                    output="工具执行被取消",
                    is_error=True,
                )
                results.append(result)
                # 工具执行完成回调（中断路径）
                if self._config.on_tool_result:
                    self._config.on_tool_result(tool_call, result)
                continue

            # 检查重复调用
            is_repeated, repeat_msg = self._repeat_detector.check(
                tool_call.name, tool_call.arguments
            )
            if is_repeated:
                logger.warning("Repeated call detected: %s - %s", tool_call.name, repeat_msg)
                result = ToolResult(output=repeat_msg, is_error=True)
                results.append(result)
                self._retry_limiter.record_failure()
                # 记忆：记录重复调用，帮助下一轮 prompt 感知循环
                if self._config.memory_enabled:
                    args_preview = str(tool_call.arguments)[:80]
                    self._memory.append_note(
                        text=f"重复调用: {tool_call.name}({args_preview})",
                        tags=["repeat", tool_call.name],
                        source="repeat_detector",
                    )
                # 记录到工具历史（标记为被拦截）
                file_path = tool_call.arguments.get("file_path") or tool_call.arguments.get("path", "")
                self._tool_history.append({
                    "turn": self._turn_count,
                    "tool_name": tool_call.name,
                    "arguments": tool_call.arguments,
                    "is_error": True,
                    "duration_ms": 0,
                    "file_path": file_path,
                    "resolved_path": "",
                    "blocked_by_repeat_detector": True,
                })
                # 工具执行完成回调（重复调用路径）
                if self._config.on_tool_result:
                    self._config.on_tool_result(tool_call, result)
                continue

            # 检查路径逃逸（文件与搜索类工具）
            if tool_call.name in ("read", "write", "edit", "grep", "glob"):
                file_path = tool_call.arguments.get("file_path") or tool_call.arguments.get("path", "")
                if file_path:
                    is_safe, path_msg = self._path_guard.check_path(file_path)
                    if not is_safe:
                        logger.warning("Path escape detected: %s", path_msg)
                        result = ToolResult(output=path_msg, is_error=True)
                        results.append(result)
                        self._retry_limiter.record_failure()
                        # 工具执行完成回调（路径逃逸路径）
                        if self._config.on_tool_result:
                            self._config.on_tool_result(tool_call, result)
                        continue

            # 权限检查（Plan Mode 下会拦截写操作）
            tool = self._registry.get(tool_call.name)
            if tool is not None:
                validation = tool.validate_input(tool_call.arguments, context)
                if not validation.is_valid:
                    result = ToolResult(
                        output=f"输入校验失败: {validation.message}",
                        is_error=True,
                    )
                    results.append(result)
                    self._retry_limiter.record_failure()
                    # 工具执行完成回调（输入校验失败路径）
                    if self._config.on_tool_result:
                        self._config.on_tool_result(tool_call, result)
                    continue

                # Session Policy：查询是否命中 session allow
                session_allowed = False
                if self._session_policy is not None:
                    from agent.permissions.session_policy import extract_permission_key
                    key = extract_permission_key(
                        tool_call.name,
                        tool_call.arguments,
                        context.cwd,
                    )
                    if key is not None:
                        session_allowed = self._session_policy.is_allowed(
                            tool_call.name, key
                        )

                perm_decision = self._permission_checker.check(
                    tool, tool_call.arguments, context
                )

                # 如果命中 session allow，跳过 ASK
                if session_allowed and perm_decision.behavior == PermissionBehavior.ASK:
                    perm_decision = PermissionDecision.allow()

                if perm_decision.behavior == PermissionBehavior.DENY:
                    logger.warning("Permission denied: %s - %s", tool_call.name, perm_decision.message)
                    result = ToolResult(
                        output=f"[权限拒绝] {perm_decision.message}",
                        is_error=True,
                    )
                    results.append(result)
                    self._retry_limiter.record_failure()
                    # 工具执行完成回调（权限拒绝路径）
                    if self._config.on_tool_result:
                        self._config.on_tool_result(tool_call, result)
                    continue
                if perm_decision.behavior == PermissionBehavior.ASK:
                    logger.warning("Permission requires confirmation: %s - %s", tool_call.name, perm_decision.message)
                    request = self._build_permission_request(
                        tool_call=tool_call,
                        context=context,
                        message=perm_decision.message,
                    )
                    if self._config.permission_handler is None:
                        result = self._build_permission_ask_result(request)
                        results.append(result)
                        self._retry_limiter.record_failure()
                        # 工具执行完成回调（无权限处理器路径）
                        if self._config.on_tool_result:
                            self._config.on_tool_result(tool_call, result)
                        continue

                    try:
                        confirmation = self._config.permission_handler(request)
                    except Exception as e:
                        logger.warning("Permission handler failed: %s", e)
                        unavailable_request = PermissionRequest(
                            tool_name=request.tool_name,
                            tool_input=request.tool_input,
                            message=f"{request.message}（确认处理器异常: {e}）",
                            preview=request.preview,
                        )
                        result = self._build_permission_ask_result(unavailable_request)
                        results.append(result)
                        self._retry_limiter.record_failure()
                        # 工具执行完成回调（处理器异常路径）
                        if self._config.on_tool_result:
                            self._config.on_tool_result(tool_call, result)
                        continue

                    if confirmation == PermissionConfirmationOutcome.UNAVAILABLE:
                        result = self._build_permission_ask_result(request)
                        results.append(result)
                        self._retry_limiter.record_failure()
                        # 工具执行完成回调（不可用路径）
                        if self._config.on_tool_result:
                            self._config.on_tool_result(tool_call, result)
                        continue

                    if confirmation == PermissionConfirmationOutcome.DENIED:
                        result = self._build_permission_rejected_result(request)
                        results.append(result)
                        self._retry_limiter.record_failure()
                        # 工具执行完成回调（被拒绝路径）
                        if self._config.on_tool_result:
                            self._config.on_tool_result(tool_call, result)
                        continue

                    if confirmation != PermissionConfirmationOutcome.APPROVED:
                        result = self._build_permission_ask_result(request)
                        results.append(result)
                        self._retry_limiter.record_failure()
                        # 工具执行完成回调（未批准路径）
                        if self._config.on_tool_result:
                            self._config.on_tool_result(tool_call, result)
                        continue

                    # Session Policy：记录 allow-once / allow-session
                    if self._session_policy is not None:
                        from agent.permissions.session_policy import extract_permission_key
                        key = extract_permission_key(
                            tool_call.name,
                            tool_call.arguments,
                            context.cwd,
                        )
                        if key is not None:
                            # 从 CLI 获取 scope（通过 _last_confirmation_scope 属性）
                            scope = "once"
                            if hasattr(self._config.permission_handler, "__self__"):
                                cli_app = self._config.permission_handler.__self__
                                if hasattr(cli_app, "_last_confirmation_scope"):
                                    scope = cli_app._last_confirmation_scope
                                    # 重置为 once，避免影响下次
                                    cli_app._last_confirmation_scope = "once"

                            self._session_policy.remember_allow(
                                tool_call.name, key, scope
                            )

                    confirmation_note = f"[已确认执行] 用户已确认执行工具 '{tool_call.name}'。"

                final_arguments = (
                    perm_decision.updated_input
                    if perm_decision.updated_input is not None
                    else tool_call.arguments
                )
            else:
                final_arguments = tool_call.arguments

            # 执行工具
            logger.info("Executing tool: %s", tool_call.name)
            start_time = time.time()
            result = self._registry.validate_and_execute(
                name=tool_call.name,
                arguments=final_arguments,
                context=context,
            )
            if confirmation_note:
                result = ToolResult(
                    output=f"{confirmation_note}\n{result.output}",
                    is_error=result.is_error,
                    new_messages=result.new_messages,
                    observation=result.observation,  # 保留 observation
                )
            duration_ms = int((time.time() - start_time) * 1000)
            results.append(result)

            # 工具执行完成回调
            if self._config.on_tool_result:
                self._config.on_tool_result(tool_call, result)

            # 记忆写入钩子
            if self._config.memory_enabled:
                self._record_memory_side_effects(tool_call, result, context)

            # 记录工具执行历史
            file_path = tool_call.arguments.get("file_path") or tool_call.arguments.get("path", "")
            resolved_path = ""
            if tool_call.name in ("read", "write", "edit") and file_path:
                import os
                resolved_path = file_path
                if not os.path.isabs(resolved_path):
                    resolved_path = os.path.join(context.cwd, resolved_path)
                resolved_path = os.path.abspath(resolved_path)
            self._tool_history.append({
                "turn": self._turn_count,
                "tool_name": tool_call.name,
                "arguments": tool_call.arguments,
                "is_error": result.is_error,
                "duration_ms": duration_ms,
                "file_path": file_path,
                "resolved_path": resolved_path,
            })

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

        设计决策:
        - 为什么优先使用 observation.preview？
          长输出（grep/bash/read）如果全部回灌，会导致上下文膨胀。
          使用 preview 让模型只看到截断后的预览，完整结果保存在 artifact。

        - 为什么保留 output 兼容？
          旧工具不传 observation，仍用 output 字段，行为不变。
          新工具返回 observation 时，loop 优先使用 preview。

        Args:
            tool_calls: 工具调用列表
            results: 工具执行结果列表
        """
        tool_result_blocks = []
        for tool_call, result in zip(tool_calls, results):
            # Observation Budget 契约：优先使用 preview，回退到 output
            content = self._resolve_observation_content(result)

            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": tool_call.id,
                "content": content,
            }
            if result.is_error:
                block["is_error"] = True
            tool_result_blocks.append(block)

        self._messages.append({
            "role": "user",
            "content": tool_result_blocks,
        })

    def _resolve_observation_content(self, result: ToolResult) -> str:
        """解析 observation 内容，决定回灌到消息历史的内容

        优先级：
        1. 如果有 observation.preview，使用 preview（截断版本）
        2. 否则使用 output（向后兼容）

        Args:
            result: 工具执行结果

        Returns:
            回灌到消息历史的文本内容
        """
        if result.observation is not None and result.observation.preview is not None:
            # 有 observation 且有 preview，使用 preview
            preview = result.observation.preview

            # 如果有 artifact 路径，附加提示
            if result.observation.artifact_path:
                preview += f"\n\n[完整输出已保存到: {result.observation.artifact_path}]"

            logger.debug(
                "Using observation preview: %d chars (was_truncated=%s, full=%d chars)",
                len(preview),
                result.observation.was_truncated,
                result.observation.full_output_chars,
            )
            return preview

        # 向后兼容：没有 observation，使用 output
        return str(result.output)

    # ========== 记忆写入钩子 ==========

    def _record_memory_side_effects(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        context: ToolUseContext,
    ) -> None:
        """工具执行后的统一记忆写入入口

        只处理文件相关工具（read/write/edit），其他工具不触发记忆写入。
        """
        paths = self._resolve_memory_paths(tool_call, context)
        if paths is None:
            return
        abs_path, display_path = paths

        if result.is_error:
            self._memory_after_tool_error(tool_call, result, display_path)
        else:
            self._memory_after_tool_success(tool_call, result, abs_path, display_path, context)

    def _resolve_memory_paths(
        self,
        tool_call: ToolCall,
        context: ToolUseContext,
    ) -> tuple[str, str] | None:
        """解析工具调用中的文件路径

        Args:
            tool_call: 工具调用
            context: 工具执行上下文

        Returns:
            (abs_path, display_path) 或 None（非文件工具）
            abs_path: 绝对路径，用于 os.stat / file_read_state
            display_path: 相对路径，用于记忆 key
        """
        if tool_call.name not in ("read", "write", "edit"):
            return None

        file_path = (
            tool_call.arguments.get("file_path")
            or tool_call.arguments.get("path", "")
        )
        if not file_path:
            return None

        import os
        abs_path = file_path
        if not os.path.isabs(abs_path):
            abs_path = os.path.join(context.cwd, abs_path)
        abs_path = os.path.abspath(abs_path)

        # 优先存相对 workspace_root 的路径
        display_path = file_path
        workspace = self._config.workspace_root
        if workspace:
            try:
                rel = os.path.relpath(abs_path, workspace)
                if not rel.startswith(".."):
                    display_path = rel
            except ValueError:
                pass  # 跨盘符，回退到原始路径

        return abs_path, display_path

    def _memory_after_tool_success(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        abs_path: str,
        display_path: str,
        context: ToolUseContext,
    ) -> None:
        """工具执行成功后的记忆写入

        read: touch_file + update_file_summary
        write/edit: touch_file + mark_pending_refresh（摘要进入待刷新状态）
        """
        import os

        self._memory.touch_file(display_path)

        if tool_call.name == "read":
            # 从 file_read_state 取原始内容（非展示层带行号的文本）
            cached = context.file_read_state.get(abs_path)
            if cached is not None:
                raw_content, cached_mtime = cached
            else:
                # 缓存未命中，重新读取
                try:
                    with open(abs_path, encoding="utf-8", errors="replace") as f:
                        raw_content = f.read()
                except OSError:
                    return

            try:
                stat = os.stat(abs_path)
                # 用绝对路径作为 key，确保 is_fresh() 的 os.stat 能正确解析
                self._memory.update_file_summary(
                    file_path=abs_path,
                    content=raw_content,
                    file_mtime=stat.st_mtime,
                    file_size=stat.st_size,
                )
            except OSError:
                pass  # 文件可能已被删除

        elif tool_call.name in ("write", "edit"):
            # 写后主动标记摘要为待刷新
            # 下次 read 时会自动重建摘要
            self._memory.mark_pending_refresh(abs_path)

            # 记录文件修改事件到 episodic notes
            self._memory.append_note(
                text=f"文件 {display_path} 被 {tool_call.name} 修改",
                tags=["file_modified", tool_call.name],
                source="tool_execution",
                kind="observation",
                entity=display_path.split("/")[-1].split("\\")[-1],
                file_path=display_path,
                importance="medium",
            )

    def _memory_after_tool_error(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        display_path: str,
    ) -> None:
        """工具执行失败后的记忆写入

        只记 read/write/edit 的错误，避免噪声。
        """
        error_msg = str(result.output)[:200]
        self._memory.append_note(
            text=f"工具 {tool_call.name} 失败: {display_path} — {error_msg}",
            tags=["error", tool_call.name],
            source="tool_execution",
        )
