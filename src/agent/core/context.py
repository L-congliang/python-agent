"""
工具执行上下文 - 对齐 Claude Code 的 ToolUseContext

这是工具执行时能访问的全部上下文信息。
工具通过这个对象与外部世界交互，而不是直接 import 全局状态。

设计决策:
- 为什么不直接传 AppState？
  因为 ToolUseContext 是工具看到的"视图"，
  不应该暴露全部 AppState，只暴露工具需要的部分。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.tools.base import Tool
    from agent.core.types import Message


@dataclass
class AbortController:
    """中断控制器 - 用于取消正在执行的工具

    对齐 Claude Code 的 AbortController。
    工具在执行过程中应该检查 is_aborted，如果为 True 则尽快退出。

    使用方式:
        controller = AbortController()
        # 用户按 Ctrl+C 时
        controller.abort()
        # 工具执行中检查
        if controller.is_aborted:
            return ToolResult(output="已取消", is_error=True)
    """

    _aborted: bool = False

    def abort(self) -> None:
        """标记为已中断"""
        self._aborted = True

    @property
    def is_aborted(self) -> bool:
        """是否已被中断"""
        return self._aborted


@dataclass
class FileReadState:
    """文件读取状态缓存 - 避免重复读取同一文件

    对齐 Claude Code 的 FileReadState。
    在一次对话中，同一个文件可能被多个工具读取，
    缓存可以避免重复的磁盘 I/O。

    使用 mtime 追踪文件修改时间，调用方可通过比较 mtime
    判断缓存是否过期（文件是否被外部修改过）。

    使用方式:
        state = FileReadState()
        result = state.get("src/main.py")  # None（首次）
        state.set("src/main.py", "print('hello')", 1718956800.0)
        result = state.get("src/main.py")  # ("print('hello')", 1718956800.0)
    """

    _cache: dict[str, tuple[str, float]] = field(default_factory=dict)

    def get(self, path: str) -> tuple[str, float] | None:
        """获取缓存的 (内容, mtime)，未缓存返回 None"""
        return self._cache.get(path)

    def set(self, path: str, content: str, mtime: float) -> None:
        """设置文件内容缓存（内容 + mtime）"""
        self._cache[path] = (content, mtime)

    def has(self, path: str) -> bool:
        """检查路径是否已缓存"""
        return path in self._cache


@dataclass
class ToolUseContext:
    """工具执行上下文

    对齐 Claude Code 的 ToolUseContext。
    工具通过这个对象访问：
    - 当前模型信息
    - 可用工具列表
    - 中断控制
    - 文件状态缓存
    - 消息历史
    - 工作目录

    设计决策:
    - 为什么不直接传 AppState？
      因为 ToolUseContext 是工具看到的"视图"，
      不应该暴露全部 AppState，只暴露工具需要的部分。
    """

    model: str
    tools: list[Tool] = field(default_factory=list)
    abort_controller: AbortController = field(default_factory=AbortController)
    file_read_state: FileReadState = field(default_factory=FileReadState)
    messages: list[Message] = field(default_factory=list)
    debug: bool = False
    verbose: bool = False

    # 扩展字段（F04 主循环会用到）
    cwd: str = "."
    max_budget_usd: float | None = None
    custom_system_prompt: str | None = None

    # 多 Agent 支持：指向当前 AgentLoop 的引用
    agent_loop: Any = None  # AgentLoop，用 Any 避免循环导入

    # Observation Budget：artifact 保存目录
    artifact_dir: str | None = None

    # Edit History：编辑历史存储
    edit_history_store: Any = None  # EditHistoryStore，用 Any 避免循环导入
