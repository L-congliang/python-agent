"""
工具协议 - 对齐 Claude Code 的 Tool 类型

设计决策:
- 为什么用 Protocol 而不是 ABC？
  Protocol 是结构化子类型，不需要继承。
  工具之间没有"是一个"的关系，不应该强制继承。
  测试时 mock 也更方便。

- 为什么有这么多属性？
  Claude Code 的 Tool 有 30+ 属性。
  我们先实现核心的 15 个，框架必须完整。
  后面加工具时，只需要实现这些属性即可。

- 为什么 build_tool 用 dataclass 而不是闭包？
  dataclass 更容易调试（能看到所有字段），
  也更容易序列化和测试。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable, Callable
from dataclasses import dataclass, field

from agent.core.types import (
    Message, ToolResult, PermissionDecision, ValidationResult,
    PermissionBehavior,
)
from agent.core.context import ToolUseContext


# ============================================================
# Tool Protocol - 对齐 Claude Code 的 Tool 类型
# ============================================================

@runtime_checkable
class Tool(Protocol):
    """工具协议 - 所有工具实现此接口

    属性分为 5 类：
    1. 基本信息: name, description, parameters
    2. 行为标记: is_enabled, is_concurrency_safe, is_read_only, is_destructive
    3. 权限检查: check_permissions, validate_input
    4. 执行: execute
    5. 序列化: to_tool_result_block, get_summary, get_user_facing_name
    """

    # === 基本信息 ===

    @property
    def name(self) -> str:
        """工具的唯一标识，LLM 用这个名字来调用工具"""
        ...

    @property
    def description(self) -> str:
        """工具的功能描述，LLM 用这个来决定什么时候调用"""
        ...

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema 格式的参数定义"""
        ...

    # === 行为标记 ===

    def is_enabled(self) -> bool:
        """是否启用此工具

        默认返回 True。可以用于 feature flag 或条件启用。
        """
        ...

    def is_concurrency_safe(self, input: dict) -> bool:
        """此工具调用是否可以并行执行

        默认返回 False（fail-closed）。
        只读工具通常可以并行，写入工具通常不行。
        """
        ...

    def is_read_only(self, input: dict) -> bool:
        """此工具调用是否只读（不修改任何状态）

        默认返回 False（fail-closed）。
        用于权限判断和 plan mode。
        """
        ...

    def is_destructive(self, input: dict) -> bool:
        """此工具调用是否不可逆（删除、覆盖、发送）

        默认返回 False。
        用于权限系统中的二次确认。
        """
        ...

    # === 权限检查 ===

    def check_permissions(
        self, input: dict, context: ToolUseContext
    ) -> PermissionDecision:
        """工具级权限检查

        在 validate_input 之后调用。
        返回 allow/deny/ask 决策。

        默认返回 allow（交给通用权限系统）。
        工具可以覆盖此方法实现自己的权限逻辑。
        """
        ...

    def validate_input(
        self, input: dict, context: ToolUseContext
    ) -> ValidationResult:
        """输入校验

        在 check_permissions 之前调用。
        检查输入是否合法（参数类型、路径是否存在等）。

        默认返回 success（不校验）。
        工具应该覆盖此方法实现自己的校验逻辑。
        """
        ...

    # === 执行 ===

    def execute(
        self, input: dict, context: ToolUseContext
    ) -> ToolResult:
        """执行工具，返回结果

        不抛异常，错误通过 ToolResult(is_error=True) 返回。
        """
        ...

    # === 序列化 ===

    def to_tool_result_block(
        self, output: Any, tool_use_id: str
    ) -> dict:
        """将工具输出转换为 Anthropic API 的 tool_result 格式

        返回格式:
        {
            "tool_use_id": "xxx",
            "type": "tool_result",
            "content": "..."  # 文本或 content blocks
        }
        """
        ...

    def get_summary(self, input: dict) -> str | None:
        """返回工具调用的简短摘要，用于 UI 显示

        例如: "Editing src/foo.py", "Running pytest"
        返回 None 表示不显示摘要。
        """
        ...

    def get_user_facing_name(self, input: dict) -> str:
        """返回用户可见的工具名称

        例如: "Read", "Edit", "Bash"
        默认返回 self.name。
        """
        ...

    def get_activity_description(self, input: dict) -> str | None:
        """返回正在进行的活动描述，用于 spinner 显示

        例如: "Reading src/foo.py", "Running pytest"
        默认返回 None。
        """
        ...


# ============================================================
# ToolImpl - build_tool 返回的具体实现
# ============================================================

@dataclass
class ToolImpl:
    """工具实现 - 由 build_tool() 工厂函数创建

    这是 Tool Protocol 的具体实现。
    工具开发者通常不需要直接使用这个类，
    而是通过 build_tool() 工厂函数创建。
    """

    # 基本信息
    _name: str
    _description: str
    _parameters: dict[str, Any]
    _execute_fn: Callable[[dict, ToolUseContext], ToolResult]

    # 可选覆盖（闭包）
    _is_enabled: Callable[[], bool] | None = None
    _is_concurrency_safe: Callable[[dict], bool] | None = None
    _is_read_only: Callable[[dict], bool] | None = None
    _is_destructive: Callable[[dict], bool] | None = None
    _check_permissions: Callable[[dict, ToolUseContext], PermissionDecision] | None = None
    _validate_input: Callable[[dict, ToolUseContext], ValidationResult] | None = None
    _to_tool_result_block: Callable[[Any, str], dict] | None = None
    _get_summary: Callable[[dict], str | None] | None = None
    _get_user_facing_name: Callable[[dict], str] | None = None
    _get_activity_description: Callable[[dict], str | None] | None = None

    # === 基本信息 ===

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    # === 行为标记（fail-closed 默认值） ===

    def is_enabled(self) -> bool:
        if self._is_enabled is not None:
            return self._is_enabled()
        return True  # 默认启用

    def is_concurrency_safe(self, input: dict) -> bool:
        if self._is_concurrency_safe is not None:
            return self._is_concurrency_safe(input)
        return False  # fail-closed：假设不安全

    def is_read_only(self, input: dict) -> bool:
        if self._is_read_only is not None:
            return self._is_read_only(input)
        return False  # fail-closed：假设会写入

    def is_destructive(self, input: dict) -> bool:
        if self._is_destructive is not None:
            return self._is_destructive(input)
        return False  # 默认非破坏性

    # === 权限检查 ===

    def check_permissions(
        self, input: dict, context: ToolUseContext
    ) -> PermissionDecision:
        if self._check_permissions is not None:
            return self._check_permissions(input, context)
        return PermissionDecision.allow()  # 默认交给通用权限系统

    def validate_input(
        self, input: dict, context: ToolUseContext
    ) -> ValidationResult:
        if self._validate_input is not None:
            return self._validate_input(input, context)
        return ValidationResult.success()  # 默认不校验

    # === 执行 ===

    def execute(
        self, input: dict, context: ToolUseContext
    ) -> ToolResult:
        return self._execute_fn(input, context)

    # === 序列化 ===

    def to_tool_result_block(
        self, output: Any, tool_use_id: str
    ) -> dict:
        if self._to_tool_result_block is not None:
            return self._to_tool_result_block(output, tool_use_id)
        # 默认：纯文本格式
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": str(output),
        }

    def get_summary(self, input: dict) -> str | None:
        if self._get_summary is not None:
            return self._get_summary(input)
        return None  # 默认不显示摘要

    def get_user_facing_name(self, input: dict) -> str:
        if self._get_user_facing_name is not None:
            return self._get_user_facing_name(input)
        return self._name  # 默认返回 name

    def get_activity_description(self, input: dict) -> str | None:
        if self._get_activity_description is not None:
            return self._get_activity_description(input)
        return None  # 默认无活动描述


# ============================================================
# build_tool 工厂函数
# ============================================================

def build_tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    execute_fn: Callable[[dict, ToolUseContext], ToolResult],
    *,
    is_enabled: Callable[[], bool] | None = None,
    is_concurrency_safe: Callable[[dict], bool] | None = None,
    is_read_only: Callable[[dict], bool] | None = None,
    is_destructive: Callable[[dict], bool] | None = None,
    check_permissions: Callable[[dict, ToolUseContext], PermissionDecision] | None = None,
    validate_input: Callable[[dict, ToolUseContext], ValidationResult] | None = None,
    to_tool_result_block: Callable[[Any, str], dict] | None = None,
    get_summary: Callable[[dict], str | None] | None = None,
    get_user_facing_name: Callable[[dict], str] | None = None,
    get_activity_description: Callable[[dict], str | None] | None = None,
) -> ToolImpl:
    """构建工具实例，填充默认值

    对齐 Claude Code 的 buildTool() 工厂函数。
    工具只需提供 name/description/parameters/execute，
    其余属性用安全的默认值填充（fail-closed）。

    默认值:
    - is_enabled → True
    - is_concurrency_safe → False（假设不安全）
    - is_read_only → False（假设会写入）
    - is_destructive → False
    - check_permissions → allow（交给通用权限系统）
    - validate_input → success（不校验）
    - to_tool_result_block → 标准格式
    - get_summary → None
    - get_user_facing_name → name
    - get_activity_description → None

    Args:
        name: 工具名称
        description: 工具描述
        parameters: JSON Schema 参数定义
        execute_fn: 执行函数
        **overrides: 可选的方法覆盖

    Returns:
        ToolImpl 实例（实现了 Tool 协议）

    Raises:
        ValueError: name 为空
    """
    if not name:
        raise ValueError("工具名称不能为空")

    return ToolImpl(
        _name=name,
        _description=description,
        _parameters=parameters,
        _execute_fn=execute_fn,
        _is_enabled=is_enabled,
        _is_concurrency_safe=is_concurrency_safe,
        _is_read_only=is_read_only,
        _is_destructive=is_destructive,
        _check_permissions=check_permissions,
        _validate_input=validate_input,
        _to_tool_result_block=to_tool_result_block,
        _get_summary=get_summary,
        _get_user_facing_name=get_user_facing_name,
        _get_activity_description=get_activity_description,
    )
