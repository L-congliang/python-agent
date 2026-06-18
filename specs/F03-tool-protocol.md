# F03: Tool Protocol + 工具注册系统

## 需求

不只是定义一个接口，而是做一个完整的工具系统：
- Protocol 定义工具的契约
- ToolRegistry 管理工具的注册和发现
- 参数校验在执行前拦截非法输入
- JSON Schema 转换让 LLM 知道怎么调用工具

## 设计决策

### 为什么用 Protocol 而不是 ABC？

```
方案 A: ABC（抽象基类）
  class Tool(ABC):
      @abstractmethod
      def execute(self, input: ToolInput) -> ToolOutput: ...

  优点: 强制子类实现，IDE 补全好
  缺点: 耦合——所有工具必须继承 Tool

方案 B: Protocol（结构化子类型）（选择这个）
  class Tool(Protocol):
      def execute(self, input: ToolInput) -> ToolOutput: ...

  优点: 不需要继承，只要方法签名匹配就行（鸭子类型）
  缺点: 不强制实现，漏了方法只在运行时报错

选择理由:
  1. 工具是独立的，不应该有继承关系
  2. Protocol 支持 @runtime_checkable，可以在注册时检查
  3. 更 Pythonic——"如果它走路像鸭子..."
  4. 方便测试——mock 工具不需要继承
```

### 为什么需要 ToolRegistry？

```
没有 Registry 的问题:
  - 主循环要硬编码所有工具：tools = [BashTool(), FileReadTool(), ...]
  - 加新工具要改主循环代码
  - 无法动态加载工具

有 Registry 的好处:
  - 工具自己注册：registry.register(BashTool())
  - 主循环从 registry 获取：tools = registry.get_all()
  - 加新工具只加一行注册代码
  - 未来可以支持插件系统
```

### 为什么在 execute 前校验参数？

```
不校验的问题:
  - 工具内部要写大量 if/else 检查参数
  - 错误信息不统一
  - LLM 传错参数时工具崩溃

用 JSON Schema 校验的好处:
  - 参数定义和校验逻辑统一
  - 错误信息自动生成
  - 工具内部只关心业务逻辑
```

## 接口定义

```python
# tools/base.py

from typing import Protocol, runtime_checkable, Any
from dataclasses import dataclass
from agent.core.types import ToolInput, ToolOutput


@runtime_checkable
class Tool(Protocol):
    """工具协议 - 所有工具实现此接口

    这是 Agent 工具系统的契约。任何实现了这四个属性/方法的类
    都可以作为工具使用，不需要继承。

    属性:
        name: 工具的唯一标识，LLM 用这个名字来调用工具
        description: 工具的功能描述，LLM 用这个来决定什么时候调用
        parameters: JSON Schema 格式的参数定义，LLM 用这个来知道怎么传参

    方法:
        execute: 执行工具，返回结果。不抛异常，错误通过 ToolOutput 返回。
    """

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def parameters(self) -> dict[str, Any]: ...

    def execute(self, input: ToolInput) -> ToolOutput: ...
```

```python
# tools/registry.py

from agent.tools.base import Tool
from agent.core.types import ToolInput, ToolOutput


class ToolRegistry:
    """工具注册表

    职责:
    - 管理工具的注册和注销
    - 提供工具查询（按名称、获取全部）
    - 将工具转换为 Anthropic API 的 tool 格式
    - 执行前校验参数
    """

    def __init__(self):
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
        """注销工具"""
        ...

    def get(self, name: str) -> Tool | None:
        """按名称获取工具"""
        ...

    def get_all(self) -> list[Tool]:
        """获取所有已注册的工具"""
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
                    "properties": {
                        "command": {"type": "string", "description": "..."}
                    },
                    "required": ["command"]
                }
            },
            ...
        ]
        """
        ...

    def execute(self, name: str, arguments: dict) -> ToolOutput:
        """执行工具（带参数校验）

        1. 查找工具
        2. 校验参数
        3. 执行工具
        4. 返回结果

        Args:
            name: 工具名称
            arguments: 参数字典

        Returns:
            ToolOutput 执行结果
        """
        ...
```

## JSON Schema 转换

LLM 需要工具的参数定义才能正确调用。Tool 的 `parameters` 属性返回 JSON Schema，`to_anthropic_tools()` 将其转换为 API 格式：

```python
# Tool 的 parameters 属性定义格式
{
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "The shell command to execute"
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds",
            "default": 30
        }
    },
    "required": ["command"]
}

# 转换后的 Anthropic API 格式
{
    "name": "bash",
    "description": "Execute a shell command",
    "input_schema": {  # ← 注意：Anthropic 用 input_schema 不是 parameters
        "type": "object",
        "properties": {...},
        "required": [...]
    }
}
```

## 参数校验

用 jsonschema 库校验：

```python
from jsonschema import validate, ValidationError

def _validate_params(self, tool: Tool, arguments: dict) -> str | None:
    """校验参数，返回错误信息或 None"""
    try:
        validate(instance=arguments, schema=tool.parameters)
        return None
    except ValidationError as e:
        return f"参数校验失败: {e.message}"
```

## 测试场景

### 1. Protocol 合规性

```python
def test_protocol_compliance():
    """实现了 name/description/parameters/execute 的类是 Tool"""
    class DummyTool:
        name = "dummy"
        description = "A dummy tool"
        parameters = {"type": "object", "properties": {}}
        def execute(self, input: ToolInput) -> ToolOutput:
            return ToolOutput(output="ok")

    assert isinstance(DummyTool(), Tool)
```

### 2. Protocol 不合规

```python
def test_not_compliant():
    """缺少方法的类不是 Tool"""
    class BadTool:
        name = "bad"
        # 缺少 description, parameters, execute

    assert not isinstance(BadTool(), Tool)
```

### 3. 注册和查询

```python
def test_register_and_get():
    """注册工具后能按名称获取"""
    registry = ToolRegistry()
    tool = DummyTool()
    registry.register(tool)
    assert registry.get("dummy") is tool

def test_register_duplicate_raises():
    """重复注册同名工具抛出 ValueError"""
    registry = ToolRegistry()
    registry.register(DummyTool())
    with pytest.raises(ValueError):
        registry.register(DummyTool())

def test_get_all():
    """get_all 返回所有已注册工具"""
    registry = ToolRegistry()
    registry.register(DummyTool())
    registry.register(AnotherTool())
    assert len(registry.get_all()) == 2
```

### 4. JSON Schema 转换

```python
def test_to_anthropic_tools():
    """正确转换为 Anthropic API 格式"""
    registry = ToolRegistry()
    registry.register(DummyTool())
    tools = registry.to_anthropic_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "dummy"
    assert "input_schema" in tools[0]
    assert tools[0]["input_schema"]["type"] == "object"
```

### 5. 参数校验

```python
def test_valid_params():
    """合法参数校验通过"""
    registry = ToolRegistry()
    registry.register(DummyTool())
    result = registry.execute("dummy", {})
    assert result.is_error is False

def test_invalid_params():
    """非法参数返回错误"""
    registry = ToolRegistry()
    registry.register(BashTool())  # 要求 command 字段
    result = registry.execute("bash", {})  # 缺少 command
    assert result.is_error is True
    assert "参数" in result.output
```

### 6. 工具未找到

```python
def test_tool_not_found():
    """调用不存在的工具返回错误"""
    registry = ToolRegistry()
    result = registry.execute("nonexistent", {})
    assert result.is_error is True
    assert "不存在" in result.output
```

## 文件结构

```
src/agent/tools/
├── __init__.py
├── base.py         ← Tool Protocol
└── registry.py     ← ToolRegistry
```

## 依赖

```toml
"jsonschema>=4.0.0",  # JSON Schema 校验
```

## 验收标准

- [ ] `Tool` Protocol 定义在 `tools/base.py`
- [ ] `ToolRegistry` 定义在 `tools/registry.py`
- [ ] `@runtime_checkable` 装饰器
- [ ] 注册时检查是否实现了 Tool 协议
- [ ] `to_anthropic_tools()` 正确转换为 API 格式
- [ ] `execute()` 执行前校验参数
- [ ] 工具未找到时返回 `ToolOutput(is_error=True)`
- [ ] 测试覆盖：合规性、注册、转换、校验、错误
- [ ] `make check` 通过

## 面试可能问的问题

```
Q: 为什么用 Protocol 不用 ABC？
A: Protocol 是结构化子类型，不需要继承。
   工具之间没有"是一个"的关系，不应该强制继承。
   测试时 mock 也更方便。

Q: 工具注册表的作用是什么？
A: 解耦——主循环不关心有哪些工具，只从 registry 获取。
   新增工具只需注册一行，不改主循环。
   未来可以扩展为插件系统。

Q: 为什么要在 execute 前校验参数？
A: LLM 传的参数不一定合法，提前校验可以：
   1. 给 LLM 返回明确的错误信息，让它重试
   2. 工具内部不用写大量防御代码
   3. 错误格式统一

Q: to_anthropic_tools 转换了什么？
A: 把 Tool 的 name/description/parameters 包装成
   Anthropic API 的 tool 定义格式。
   注意 Anthropic 用 input_schema 而不是 parameters。
```
