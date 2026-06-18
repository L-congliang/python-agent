"""
类型定义 - Agent 的基础数据结构

这是整个 Agent 的地基，定义了：
- Role: 消息角色
- ToolCall: LLM 请求调用工具
- ToolCallResult: 工具执行结果（返回给 API）
- Message: 对话消息
- StreamEvent: 流式事件
- PermissionDecision: 权限决策（对齐 Claude Code）
- ValidationResult: 输入校验结果（对齐 Claude Code）
- ToolResult: 工具执行结果（对齐 Claude Code，工具返回给注册表）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class Role(Enum):
    """消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ============================================================
# 权限系统（对齐 Claude Code 的 PermissionDecision）
# ============================================================

class PermissionBehavior(Enum):
    """权限决策行为"""
    ALLOW = "allow"     # 允许执行
    DENY = "deny"       # 拒绝执行
    ASK = "ask"         # 询问用户


@dataclass
class PermissionDecision:
    """权限决策结果

    对齐 Claude Code 的 PermissionDecision 类型。
    - allow: 允许执行，可附带修改后的 input
    - deny: 拒绝执行，附带原因
    - ask: 询问用户，附带提示信息
    """
    behavior: PermissionBehavior
    message: str = ""
    updated_input: dict | None = None  # allow 时可修改 input

    @classmethod
    def allow(cls, updated_input: dict | None = None) -> PermissionDecision:
        """允许执行"""
        return cls(behavior=PermissionBehavior.ALLOW, updated_input=updated_input)

    @classmethod
    def deny(cls, message: str) -> PermissionDecision:
        """拒绝执行"""
        return cls(behavior=PermissionBehavior.DENY, message=message)

    @classmethod
    def ask(cls, message: str) -> PermissionDecision:
        """询问用户"""
        return cls(behavior=PermissionBehavior.ASK, message=message)


# ============================================================
# 校验结果（对齐 Claude Code 的 ValidationResult）
# ============================================================

@dataclass
class ValidationResult:
    """输入校验结果

    对齐 Claude Code 的 ValidationResult 类型。
    - success: 校验通过
    - failure: 校验失败，附带错误信息和错误码
    """
    is_valid: bool
    message: str = ""
    error_code: int = 0

    @classmethod
    def success(cls) -> ValidationResult:
        """校验通过"""
        return cls(is_valid=True)

    @classmethod
    def failure(cls, message: str, error_code: int = 0) -> ValidationResult:
        """校验失败"""
        return cls(is_valid=False, message=message, error_code=error_code)


# ============================================================
# 工具执行结果（对齐 Claude Code 的 ToolResult）
# ============================================================

@dataclass
class ToolResult:
    """工具执行结果

    对齐 Claude Code 的 ToolResult 类型。
    这是工具 execute() 方法的返回值，由 ToolRegistry 处理。

    - output: 输出内容（文本或结构化数据）
    - is_error: 是否出错
    - new_messages: 可选，注入到对话历史的新消息
    """
    output: Any
    is_error: bool = False
    new_messages: list[Message] | None = None


# ============================================================
# API 通信类型
# ============================================================

@dataclass
class ToolCall:
    """LLM 请求调用工具"""
    id: str             # 调用 ID
    name: str           # 工具名称
    arguments: dict     # 参数


@dataclass
class ToolCallResult:
    """工具执行结果（返回给 API）

    用于构造 Anthropic API 的 tool_result 消息。
    与 ToolResult 的区别：
    - ToolResult: 工具返回给注册表（含 new_messages）
    - ToolCallResult: 注册表返回给 API（含 tool_call_id）
    """
    tool_call_id: str   # 对应的调用 ID
    output: str         # 输出内容
    is_error: bool = False


@dataclass
class Message:
    """对话消息"""
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_results: list[ToolCallResult] | None = None


@dataclass
class StreamEvent:
    """流式事件"""
    type: str           # "text", "tool_use", "tool_result"
    content: Any = None
