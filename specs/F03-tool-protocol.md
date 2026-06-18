# F03: Tool Protocol + 工具注册系统（对齐 Claude Code）

> **参考文档**: `docs/claude-code-architecture.md` 第 2 节 Tool 系统

## 设计目标

不是做一个"能用就行"的工具接口，而是做一个**工业级的工具框架**：
- 完整的行为标记（权限、并发、只读、破坏性）
- 两层权限检查（validateInput + checkPermissions）
- 统一的结果序列化
- 工厂函数 + 默认值（fail-closed）
- 为 F04 主循环提供完整的 ToolUseContext

## 与 Claude Code 的对齐点

| Claude Code | python-agent | 说明 |
|-------------|--------------|------|
| `buildTool()` 工厂 | `build_tool()` | 填充默认值 |
| `ToolDef` 类型 | `ToolDef` TypedDict | 部分属性可选 |
| `ToolUseContext` | `ToolUseContext` dataclass | 工具执行上下文 |
| `PermissionDecision` | `PermissionDecision` | 权限决策 |
| `ValidationResult` | `ValidationResult` | 输入校验结果 |
| `ToolResult` | `ToolResult` dataclass | 工具执行结果 |
| `isConcurrencySafe` | `is_concurrency_safe` | 并发安全标记 |
| `isReadOnly` | `is_read_only` | 只读标记 |
| `isDestructive` | `is_destructive` | 破坏性标记 |
| `checkPermissions` | `check_permissions` | 工具级权限 |
| `validateInput` | `validate_input` | 输入校验 |
| `mapToolResultToToolResultBlockParam` | `to_tool_result_block` | 序列化给 API |

## 文件结构

```
src/agent/
├── core/
│   ├── types.py          # 已有，需扩展
│   └── context.py        # 新增：ToolUseContext
├── tools/
│   ├── __init__.py
│   ├── base.py           # 新增：Tool Protocol + build_tool
│   └── registry.py       # 新增：ToolRegistry
└── permissions/
    └── __init__.py
```

---

## 接口定义

### 1. 类型扩展（`core/types.py`）

在现有类型基础上，新增以下类型：

```python
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


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
    def allow(cls, updated_input: dict | None = None) -> "PermissionDecision":
        return cls(behavior=PermissionBehavior.ALLOW, updated_input=updated_input)

    @classmethod
    def deny(cls, message: str) -> "PermissionDecision":
        return cls(behavior=PermissionBehavior.DENY, message=message)

    @classmethod
    def ask(cls, message: str) -> "PermissionDecision":
        return cls(behavior=PermissionBehavior.ASK, message=message)


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
    def success(cls) -> "ValidationResult":
        return cls(is_valid=True)

    @classmethod
    def failure(cls, message: str, error_code: int = 0) -> "ValidationResult":
        return cls(is_valid=False, message=message, error_code=error_code)


@dataclass
class ToolResult:
    """工具执行结果

    对齐 Claude Code 的 ToolResult 类型。
    - output: 输出内容（文本或结构化数据）
    - is_error: 是否出错
    - new_messages: 可选，注入到对话历史的新消息
    """
    output: Any
    is_error: bool = False
    new_messages: list["Message"] | None = None
```

### 2. ToolUseContext（`core/context.py`）

```python
"""
工具执行上下文 - 对齐 Claude Code 的 ToolUseContext

这是工具执行时能访问的全部上下文信息。
工具通过这个对象与外部世界交互，而不是直接 import 全局状态。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from agent.tools.base import Tool
    from agent.core.types import Message


@dataclass
class AbortController:
    """中断控制器 - 用于取消正在执行的工具"""
    _aborted: bool = False

    def abort(self) -> None:
        self._aborted = True

    @property
    def is_aborted(self) -> bool:
        return self._aborted


@dataclass
class FileReadState:
    """文件读取状态缓存 - 避免重复读取同一文件"""
    _cache: dict[str, str] = field(default_factory=dict)

    def get(self, path: str) -> str | None:
        return self._cache.get(path)

    def set(self, path: str, content: str) -> None:
        self._cache[path] = content

    def has(self, path: str) -> bool:
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
    - 应用状态
    - 消息历史

    设计决策:
    - 为什么不直接传 AppState？
      因为 ToolUseContext 是工具看到的"视图"，
      不应该暴露全部 AppState，只暴露工具需要的部分。
    """
    model: str
    tools: list["Tool"]
    abort_controller: AbortController = field(default_factory=AbortController)
    file_read_state: FileReadState = field(default_factory=FileReadState)
    messages: list["Message"] = field(default_factory=list)
    debug: bool = False
    verbose: bool = False

    # 扩展字段（F04 主循环会用到）
    cwd: str = "."
    max_budget_usd: float | None = None
    custom_system_prompt: str | None = None
```

### 3. Tool Protocol（`tools/base.py`）

```python
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
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable, TypedDict
from dataclasses import dataclass, field

from agent.core.types import (
    Message, ToolResult, PermissionDecision, ValidationResult
)
from agent.core.context import ToolUseContext


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
```

### 4. build_tool 工厂函数（`tools/base.py`）

```python
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
) -> Tool:
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
        完整的 Tool 实例
    """
    ...
```

### 5. ToolRegistry（`tools/registry.py`）

```python
"""
工具注册表 - 管理工具的注册和发现

对齐 Claude Code 的 tools.ts 中的 getAllBaseTools() 和相关函数。
"""

from agent.tools.base import Tool
from agent.core.types import ToolResult, PermissionDecision, ValidationResult
from agent.core.context import ToolUseContext


class ToolRegistry:
    """工具注册表

    职责:
    - 管理工具的注册和注销
    - 提供工具查询（按名称、获取全部）
    - 将工具转换为 Anthropic API 的 tool 格式
    - 执行前校验 + 权限检查 + 执行
    - 按权限规则过滤工具列表

    设计决策:
    - 为什么不直接用 dict？
      因为需要类型检查、格式转换、统一执行流程。
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具

        Args:
            tool: 实现了 Tool 协议的对象

        Raises:
            TypeError: tool 没有实现 Tool 协议
            ValueError: 工具名称已存在
        """
        ...

    def unregister(self, name: str) -> None:
        """注销工具

        Args:
            name: 工具名称

        Raises:
            KeyError: 工具不存在
        """
        ...

    def get(self, name: str) -> Tool | None:
        """按名称获取工具

        Args:
            name: 工具名称

        Returns:
            Tool 实例，或 None
        """
        ...

    def get_all(self) -> list[Tool]:
        """获取所有已注册的工具"""
        ...

    def get_enabled_tools(self) -> list[Tool]:
        """获取所有启用的工具

        过滤掉 is_enabled() 返回 False 的工具。
        """
        ...

    def to_anthropic_tools(self) -> list[dict]:
        """转换为 Anthropic API 的 tools 格式

        返回格式:
        [
            {
                "name": "bash",
                "description": "Execute a shell command",
                "input_schema": {
                    "type": "object",
                    "properties": {...},
                    "required": [...]
                }
            },
            ...
        ]
        """
        ...

    def validate_and_execute(
        self,
        name: str,
        arguments: dict,
        context: ToolUseContext,
    ) -> ToolResult:
        """校验权限 + 校验输入 + 执行工具

        完整的执行流程:
        1. 查找工具
        2. 检查 is_enabled
        3. validate_input（输入校验）
        4. check_permissions（权限检查）
        5. execute（执行）
        6. 返回结果

        任何步骤失败都返回 ToolResult(is_error=True)。

        Args:
            name: 工具名称
            arguments: 参数字典
            context: 工具执行上下文

        Returns:
            ToolResult 执行结果
        """
        ...
```

---

## 测试场景

### 1. build_tool 默认值

```python
def test_build_tool_defaults():
    """build_tool 填充安全的默认值"""
    tool = build_tool(
        name="test",
        description="A test tool",
        parameters={"type": "object", "properties": {}},
        execute_fn=lambda input, ctx: ToolResult(output="ok"),
    )
    assert tool.is_enabled() is True
    assert tool.is_concurrency_safe({}) is False  # fail-closed
    assert tool.is_read_only({}) is False          # fail-closed
    assert tool.is_destructive({}) is False
    assert tool.validate_input({}, mock_context).is_valid is True
    assert tool.check_permissions({}, mock_context).behavior == "allow"
```

### 2. build_tool 覆盖

```python
def test_build_tool_overrides():
    """可以覆盖默认值"""
    tool = build_tool(
        name="read",
        description="Read file",
        parameters={...},
        execute_fn=lambda input, ctx: ToolResult(output="content"),
        is_read_only=lambda input: True,
        is_concurrency_safe=lambda input: True,
    )
    assert tool.is_read_only({}) is True
    assert tool.is_concurrency_safe({}) is True
```

### 3. ToolRegistry 注册和查询

```python
def test_register_and_get():
    """注册工具后能按名称获取"""
    registry = ToolRegistry()
    tool = build_tool(name="test", ...)
    registry.register(tool)
    assert registry.get("test") is tool

def test_register_duplicate_raises():
    """重复注册同名工具抛出 ValueError"""
    registry = ToolRegistry()
    registry.register(build_tool(name="test", ...))
    with pytest.raises(ValueError):
        registry.register(build_tool(name="test", ...))

def test_get_enabled_tools():
    """get_enabled_tools 过滤掉禁用的工具"""
    registry = ToolRegistry()
    registry.register(build_tool(name="a", ..., is_enabled=lambda: True))
    registry.register(build_tool(name="b", ..., is_enabled=lambda: False))
    assert len(registry.get_enabled_tools()) == 1
```

### 4. to_anthropic_tools 转换

```python
def test_to_anthropic_tools():
    """正确转换为 Anthropic API 格式"""
    registry = ToolRegistry()
    registry.register(build_tool(
        name="bash",
        description="Execute shell command",
        parameters={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
        execute_fn=lambda i, c: ToolResult(output="ok"),
    ))
    tools = registry.to_anthropic_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "bash"
    assert "input_schema" in tools[0]
    assert tools[0]["input_schema"]["type"] == "object"
```

### 5. validate_and_execute 完整流程

```python
def test_validate_and_execute_success():
    """正常执行流程"""
    registry = ToolRegistry()
    registry.register(build_tool(
        name="test",
        description="test",
        parameters={"type": "object", "properties": {}},
        execute_fn=lambda i, c: ToolResult(output="ok"),
    ))
    result = registry.validate_and_execute("test", {}, mock_context)
    assert result.is_error is False
    assert result.output == "ok"

def test_validate_and_execute_not_found():
    """工具不存在"""
    registry = ToolRegistry()
    result = registry.validate_and_execute("nonexistent", {}, mock_context)
    assert result.is_error is True
    assert "不存在" in result.output

def test_validate_and_execute_validation_failed():
    """输入校验失败"""
    registry = ToolRegistry()
    registry.register(build_tool(
        name="test",
        description="test",
        parameters={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        execute_fn=lambda i, c: ToolResult(output="ok"),
        validate_input=lambda i, c: ValidationResult.failure("缺少 x 参数"),
    ))
    result = registry.validate_and_execute("test", {}, mock_context)
    assert result.is_error is True
    assert "x" in result.output

def test_validate_and_execute_permission_denied():
    """权限被拒绝"""
    registry = ToolRegistry()
    registry.register(build_tool(
        name="test",
        description="test",
        parameters={...},
        execute_fn=lambda i, c: ToolResult(output="ok"),
        check_permissions=lambda i, c: PermissionDecision.deny("没有权限"),
    ))
    result = registry.validate_and_execute("test", {}, mock_context)
    assert result.is_error is True
    assert "权限" in result.output
```

### 6. PermissionDecision 工厂方法

```python
def test_permission_decision_factories():
    """工厂方法创建正确的决策"""
    allow = PermissionDecision.allow()
    assert allow.behavior == PermissionBehavior.ALLOW

    deny = PermissionDecision.deny("原因")
    assert deny.behavior == PermissionBehavior.DENY
    assert deny.message == "原因"

    ask = PermissionDecision.ask("确认？")
    assert ask.behavior == PermissionBehavior.ASK
    assert ask.message == "确认？"
```

---

## 依赖

```toml
# 已有依赖，无需新增
"jsonschema>=4.0.0",  # JSON Schema 校验
```

## 验收标准

- [ ] `PermissionDecision` dataclass 在 `core/types.py`
- [ ] `ValidationResult` dataclass 在 `core/types.py`
- [ ] `ToolResult` dataclass 在 `core/types.py`
- [ ] `ToolUseContext` dataclass 在 `core/context.py`
- [ ] `AbortController` 在 `core/context.py`
- [ ] `FileReadState` 在 `core/context.py`
- [ ] `Tool` Protocol 在 `tools/base.py`，含 15 个属性/方法
- [ ] `build_tool()` 工厂函数，填充 fail-closed 默认值
- [ ] `ToolRegistry` 在 `tools/registry.py`
- [ ] `register()` 含类型检查和重复检查
- [ ] `to_anthropic_tools()` 正确转换格式
- [ ] `validate_and_execute()` 完整流程：查找→校验→权限→执行
- [ ] 测试覆盖所有场景
- [ ] `make check` 通过

## 面试可能问的问题

```
Q: 为什么 Tool Protocol 有这么多属性？
A: Claude Code 的 Tool 有 30+ 属性，我们先实现 15 个核心的。
   每个属性都有明确用途：
   - is_concurrency_safe: 主循环决定是否并行执行工具
   - is_read_only: plan mode 下只允许只读工具
   - is_destructive: 权限系统中需要二次确认
   - check_permissions: 工具自定义权限逻辑
   - validate_input: 提前拦截非法输入，给 LLM 明确错误

Q: build_tool 的默认值为什么是 fail-closed？
A: 安全第一。假设：
   - is_concurrency_safe=False（不安全）→ 主循环串行执行
   - is_read_only=False（会写入）→ plan mode 下不能用
   - check_permissions=allow（交给通用系统）→ 工具不自己判断权限时，由通用权限系统处理

Q: validate_input 和 check_permissions 的顺序？
A: 先 validate_input，再 check_permissions。
   因为：如果输入本身不合法，没必要检查权限。
   Claude Code 也是这个顺序。

Q: ToolUseContext 为什么不直接用 AppState？
A: 最小暴露原则。工具只需要知道：
   - 当前模型
   - 可用工具
   - 中断控制
   - 文件缓存
   不需要知道用户设置、权限模式、UI 状态等。
```
