"""
核心模块 - Agent 的核心组件

包含:
- types: 基础数据类型（Role, Message, ToolCall 等）
- context: 工具执行上下文（ToolUseContext, AbortController）
- model: mimo API 客户端（MimoClient, ModelConfig, StreamResult）
- loop: Agent 主循环（AgentLoop, LoopConfig）
"""

from .types import (
    Role, ToolCall, ToolCallResult, ToolResult, Message, StreamEvent,
    PermissionBehavior, PermissionDecision, ValidationResult,
)
from .context import ToolUseContext, AbortController, FileReadState
from .model import MimoClient, ModelConfig, load_config, StreamResult

# 注意: LoopConfig 和 AgentLoop 不在这里导入，
# 因为 agent.core.loop → agent.tools.registry → agent.tools.base → agent.core.types
# 会形成循环导入。使用者应直接 from agent.core.loop import ...

__all__ = [
    # types
    "Role",
    "ToolCall",
    "ToolCallResult",
    "ToolResult",
    "Message",
    "StreamEvent",
    "PermissionBehavior",
    "PermissionDecision",
    "ValidationResult",
    # context
    "ToolUseContext",
    "AbortController",
    "FileReadState",
    # model
    "MimoClient",
    "ModelConfig",
    "load_config",
    "StreamResult",
]
