"""
类型定义 - Agent 的基础数据结构

这是整个 Agent 的地基，定义了：
- ToolInput: 工具输入
- ToolOutput: 工具输出
- ToolCall: LLM 请求调用工具
- ToolResult: 工具执行结果
- Message: 对话消息
"""

from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class Role(Enum):
    """消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class ToolInput:
    """工具输入参数"""
    name: str           # 工具名称
    arguments: dict     # 参数字典


@dataclass
class ToolOutput:
    """工具执行结果"""
    output: str         # 输出内容
    is_error: bool = False  # 是否出错


@dataclass
class ToolCall:
    """LLM 请求调用工具"""
    id: str             # 调用 ID
    name: str           # 工具名称
    arguments: dict     # 参数


@dataclass
class ToolResult:
    """工具执行结果（返回给 LLM）"""
    tool_call_id: str   # 对应的调用 ID
    output: str         # 输出内容
    is_error: bool = False


@dataclass
class Message:
    """对话消息"""
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_results: list[ToolResult] | None = None


@dataclass
class StreamEvent:
    """流式事件"""
    type: str           # "text", "tool_use", "tool_result"
    content: Any = None
