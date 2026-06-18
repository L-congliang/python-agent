# F01: Tool Protocol 接口

## 需求

定义一个统一的 `Tool` 协议（Protocol），所有具体工具（Bash、FileRead、Grep 等）都实现此接口。
Agent 主循环通过这个协议调用工具，不需要知道具体工具的实现细节。

## 接口定义

```python
from typing import Protocol, runtime_checkable
from agent.core.types import ToolInput, ToolOutput

@runtime_checkable
class Tool(Protocol):
    """工具协议 - 所有工具实现此接口"""

    @property
    def name(self) -> str:
        """工具名称，用于 LLM 识别（如 "bash", "file_read"）"""
        ...

    @property
    def description(self) -> str:
        """工具描述，告诉 LLM 这个工具能做什么"""
        ...

    @property
    def parameters(self) -> dict:
        """参数 schema，JSON Schema 格式，告诉 LLM 如何传参"""
        ...

    def execute(self, input: ToolInput) -> ToolOutput:
        """执行工具，返回结果"""
        ...
```

### 属性说明

| 属性 | 类型 | 作用 | 示例 |
|------|------|------|------|
| `name` | `str` | 工具的唯一标识 | `"bash"`, `"file_read"` |
| `description` | `str` | 给 LLM 看的功能描述 | `"Execute a shell command"` |
| `parameters` | `dict` | JSON Schema 格式的参数定义 | `{"type": "object", "properties": {...}}` |

### execute 方法

- **输入**: `ToolInput`（包含 `name` 和 `arguments`）
- **输出**: `ToolOutput`（包含 `output` 字符串和 `is_error` 布尔值）
- **异常**: 不抛出异常，所有错误通过 `ToolOutput(is_error=True)` 返回

## 数据类型（已有，来自 types.py）

```python
@dataclass
class ToolInput:
    name: str           # 工具名称
    arguments: dict     # 参数字典

@dataclass
class ToolOutput:
    output: str         # 输出内容
    is_error: bool = False  # 是否出错
```

## 测试场景

### 1. 协议合规性

```python
def test_tool_protocol_compliance():
    """任何实现了 name/description/parameters/execute 的类都是 Tool"""
    class DummyTool:
        name = "dummy"
        description = "A dummy tool"
        parameters = {"type": "object", "properties": {}}
        def execute(self, input: ToolInput) -> ToolOutput:
            return ToolOutput(output="ok")

    assert isinstance(DummyTool(), Tool)
```

### 2. 正常执行

```python
def test_execute_returns_output():
    """execute 返回 ToolOutput，is_error 默认 False"""
    tool = DummyTool()
    result = tool.execute(ToolInput(name="dummy", arguments={}))
    assert result.output == "ok"
    assert result.is_error is False
```

### 3. 错误处理

```python
def test_execute_error_returns_tool_output():
    """工具执行失败时，返回 ToolOutput(is_error=True)，不抛异常"""
    class FailingTool:
        name = "fail"
        description = "Always fails"
        parameters = {}
        def execute(self, input: ToolInput) -> ToolOutput:
            return ToolOutput(output="something went wrong", is_error=True)

    tool = FailingTool()
    result = tool.execute(ToolInput(name="fail", arguments={}))
    assert result.is_error is True
    assert "went wrong" in result.output
```

### 4. parameters 返回合法 JSON Schema

```python
def test_parameters_is_valid_schema():
    """parameters 必须包含 type 和 properties 字段"""
    tool = DummyTool()
    schema = tool.parameters
    assert "type" in schema
    assert schema["type"] == "object"
```

## 文件结构

```
src/agent/tools/
├── __init__.py
└── base.py          ← Tool 协议定义在这里
```

## 验收标准

- [ ] `Tool` 协议定义在 `tools/base.py`
- [ ] 包含 `name`、`description`、`parameters` 三个属性
- [ ] 包含 `execute(self, input: ToolInput) -> ToolOutput` 方法
- [ ] 使用 `@runtime_checkable` 装饰器
- [ ] 有 4 个测试用例覆盖上述场景
- [ ] `make check` 通过
