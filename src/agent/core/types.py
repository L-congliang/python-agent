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


class PermissionConfirmationOutcome(Enum):
    """权限确认结果。"""
    APPROVED = "approved"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"


@dataclass
class PermissionConfirmationResult:
    """权限确认结果（带作用域）

    Attributes:
        outcome: 确认结果
        scope: 作用域（once 或 session），只在 APPROVED 时有效
    """
    outcome: PermissionConfirmationOutcome
    scope: str = "once"  # "once" 或 "session"


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

    @property
    def reason(self) -> str:
        """兼容旧代码使用的 reason 字段名。"""
        return self.message

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


@dataclass
class PermissionRequest:
    """交互式权限确认请求。"""
    tool_name: str
    tool_input: dict[str, Any]
    message: str
    preview: str | None = None


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
# 观察元数据（Observation Budget 契约）
# ============================================================


@dataclass
class ObservationMetadata:
    """观察元数据 - 工具输出的双层契约

    设计决策:
    - 为什么需要双层契约？
      长输出（grep/bash/read）如果全部回灌到消息历史，会导致上下文膨胀。
      双层契约让工具同时提供 preview（模型可见）和 artifact（用户可追溯）。

    - 为什么 preview 是可选的？
      保持向后兼容：旧工具只返回 output，新工具返回 output + observation。
      没有 preview 时，loop 仍用 output 字段，行为不变。

    - artifact_path 的作用？
      当输出被截断时，完整结果保存到文件，artifact_path 记录路径。
      用户可以通过路径找到完整结果，模型只看到 preview。

    Attributes:
        preview: 模型可见的预览内容（截断后的版本）
        artifact_path: 完整输出保存的文件路径
        was_truncated: 输出是否被截断
        full_output_chars: 完整输出的字符数（用于统计）
    """
    preview: str | None = None
    artifact_path: str | None = None
    was_truncated: bool = False
    full_output_chars: int = 0


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
    - observation: 可选，观察元数据（preview + artifact 双层契约）
    """
    output: Any
    is_error: bool = False
    new_messages: list[Message] | None = None
    observation: ObservationMetadata | None = None


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
    """流式事件

    AgentLoop 产生的事件类型，由 UI 层消费渲染。
    对齐 Claude Code 的事件系统。

    事件类型:
    - text: 模型回复的文本 chunk
    - tool_call: 模型请求调用工具
    - tool_result: 工具执行结果
    """
    type: str           # "text", "tool_call", "tool_result"
    content: Any = None
    tool_name: str | None = None      # tool_call 时的工具名
    tool_input: dict | None = None    # tool_call 时的参数
    is_error: bool = False            # tool_result 时是否出错
    observation: ObservationMetadata | None = None  # tool_result 时的观察元数据
