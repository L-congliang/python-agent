# F04: Agent 主循环（对齐 Claude Code）

> **参考文档**: `docs/claude-code-architecture.md` 第 3 节 主循环
> **前置依赖**: F03 Tool Protocol

## 设计目标

实现 Agent 的核心循环：**用户输入 → 模型回复 → 工具调用 → 结果返回 → 循环**

这不是一个简单的 while 循环，而是一个完整的执行引擎：
- 流式输出
- 工具调用解析和执行
- 错误恢复（重试、降级）
- 上下文管理（消息历史、token 估算）
- 中断支持
- 对话轮次控制

## 与 Claude Code 的对齐点

| Claude Code (query.ts) | python-agent (loop.py) | 说明 |
|------------------------|------------------------|------|
| `QueryParams` | `LoopConfig` | 循环配置 |
| `query()` 主函数 | `AgentLoop.run()` | 主循环入口 |
| 流式解析 tool_use | 流式解析 tool_use | 实时解析工具调用 |
| `StreamingToolExecutor` | `ToolExecutor` | 工具执行器 |
| Auto Compact | 暂不实现 | F10 再做 |
| Max Output Recovery | 暂不实现 | 后续优化 |
| Token Budget | 暂不实现 | 后续优化 |

## 文件结构

```
src/agent/
├── core/
│   ├── loop.py           # 新增：Agent 主循环
│   ├── model.py          # 已有
│   ├── types.py          # 已有（F03 扩展后）
│   └── context.py        # F03 新增
└── tools/
    ├── base.py           # F03 新增
    └── registry.py       # F03 新增
```

---

## 接口定义

### 1. LoopConfig（`core/loop.py`）

```python
@dataclass
class LoopConfig:
    """主循环配置

    对齐 Claude Code 的 QueryParams。
    控制循环行为的所有参数。
    """
    # 模型配置
    model: str = "mimo-v2.5-pro"
    max_tokens: int = 4096

    # 循环控制
    max_turns: int = 50           # 最大轮次（防止无限循环）
    max_tool_calls: int = 100     # 最大工具调用次数

    # 系统提示
    system_prompt: str = ""
    append_system_prompt: str = ""  # 追加的系统提示

    # 调试
    debug: bool = False
    verbose: bool = False
```

### 2. AgentLoop（`core/loop.py`）

```python
class AgentLoop:
    """Agent 主循环

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
    """

    def __init__(
        self,
        client: MimoClient,
        registry: ToolRegistry,
        config: LoopConfig | None = None,
    ) -> None:
        """初始化主循环

        Args:
            client: mimo API 客户端
            registry: 工具注册表
            config: 循环配置（可选，有默认值）
        """
        ...

    def run(self, user_input: str) -> str:
        """运行一轮完整的对话

        流程:
        1. 构建消息（system prompt + 历史 + 用户输入）
        2. 调用模型（流式）
        3. 解析响应（文本 + tool_use）
        4. 如果有 tool_use:
           a. 校验权限
           b. 执行工具
           c. 注入结果到消息历史
           d. 回到步骤 2
        5. 如果没有 tool_use:
           a. 返回模型回复
        6. 轮次超限 → 返回错误信息

        Args:
            user_input: 用户输入的文本

        Returns:
            模型的最终回复文本

        Raises:
            KeyboardInterrupt: 用户中断（Ctrl+C）
        """
        ...

    def run_stream(self, user_input: str) -> Iterator[str]:
        """运行一轮对话，流式返回文本

        与 run() 类似，但文本部分流式输出。
        工具调用时仍然阻塞等待执行完成。

        Yields:
            文本 chunk
        """
        ...

    def reset(self) -> None:
        """重置对话历史

        开始新的对话时调用。
        """
        ...

    @property
    def messages(self) -> list[dict]:
        """获取当前消息历史（只读）"""
        ...

    @property
    def turn_count(self) -> int:
        """当前轮次"""
        ...

    @property
    def tool_call_count(self) -> int:
        """当前工具调用次数"""
        ...

    def abort(self) -> None:
        """中断当前执行"""
        ...
```

### 3. 内部方法

```python
class AgentLoop:
    # ... 公开方法 ...

    def _build_messages(self, user_input: str) -> list[dict]:
        """构建 API 调用的消息列表

        格式:
        [
            {"role": "user", "content": "用户输入"},
            {"role": "assistant", "content": "模型回复"},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "xxx", "content": "..."}
            ]},
            ...
        ]
        """
        ...

    def _build_system_prompt(self) -> str:
        """构建系统提示

        组合:
        1. config.system_prompt（基础提示）
        2. config.append_system_prompt（追加提示）
        3. 工具使用说明（动态生成）
        """
        ...

    def _parse_response(self, response_text: str) -> tuple[str, list[ToolCall]]:
        """解析模型响应，提取文本和工具调用

        Args:
            response_text: 模型的完整响应文本

        Returns:
            (文本内容, 工具调用列表)
        """
        ...

    def _execute_tool_call(
        self, tool_call: ToolCall, context: ToolUseContext
    ) -> ToolResult:
        """执行单个工具调用

        流程:
        1. 从 registry 获取工具
        2. validate_input
        3. check_permissions
        4. execute
        5. 返回结果

        Args:
            tool_call: 工具调用信息
            context: 工具执行上下文

        Returns:
            ToolResult 执行结果
        """
        ...

    def _handle_tool_results(
        self, tool_calls: list[ToolCall], results: list[ToolResult]
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
        """
        ...
```

---

## 核心流程图

```
run(user_input)
    │
    ▼
┌─────────────────────────────────────────────┐
│ 构建 messages = 历史 + user_input            │
│ 构建 system_prompt                           │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ 调用 model.chat_stream(messages, system)     │
│ 流式接收响应                                  │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ 解析响应: text + tool_use blocks             │
└─────────────────────────────────────────────┘
    │
    ├─ 有 tool_use ──────────────────────────────┐
    │                                            ▼
    │                    ┌─────────────────────────────────────┐
    │                    │ 遍历 tool_calls:                     │
    │                    │   1. validate_input                  │
    │                    │   2. check_permissions               │
    │                    │   3. execute                         │
    │                    │   4. 收集 results                    │
    │                    └─────────────────────────────────────┘
    │                                            │
    │                                            ▼
    │                    ┌─────────────────────────────────────┐
    │                    │ 注入 results 到 messages             │
    │                    │ tool_call_count += len(tool_calls)  │
    │                    └─────────────────────────────────────┘
    │                                            │
    │                                            ▼
    │                                    回到 "调用 model" ↑
    │
    └─ 无 tool_use ──────────────────────────────┐
                                                 ▼
                                    ┌─────────────────────────┐
                                    │ 返回 text 给用户         │
                                    │ messages.append(reply)  │
                                    └─────────────────────────┘
```

---

## 消息格式

### Anthropic API 消息格式

```python
# 用户消息
{"role": "user", "content": "帮我写一个 hello world"}

# 模型回复（纯文本）
{"role": "assistant", "content": "好的，我来创建一个文件"}

# 模型回复（含工具调用）
{"role": "assistant", "content": [
    {"type": "text", "text": "我来创建文件"},
    {"type": "tool_use", "id": "toolu_xxx", "name": "file_write", "input": {...}}
]}

# 工具结果
{"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "toolu_xxx", "content": "文件已创建"}
]}

# 工具结果（错误）
{"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "toolu_xxx", "content": "权限不足", "is_error": true}
]}
```

---

## 测试场景

### 1. 纯文本对话

```python
def test_simple_text_response():
    """模型返回纯文本，不调用工具"""
    client = mock_client(response="你好！")
    registry = ToolRegistry()
    loop = AgentLoop(client, registry)

    reply = loop.run("你好")
    assert reply == "你好！"
    assert loop.turn_count == 1
    assert loop.tool_call_count == 0
```

### 2. 单次工具调用

```python
def test_single_tool_call():
    """模型调用一次工具，然后返回结果"""
    client = mock_client_stream([
        # 第一次回复：调用工具
        {"text": "我来读取文件", "tool_use": {"id": "t1", "name": "read", "input": {"path": "test.txt"}}},
        # 第二次回复：基于工具结果回复
        {"text": "文件内容是 hello"},
    ])
    registry = ToolRegistry()
    registry.register(mock_read_tool(return_value="hello"))
    loop = AgentLoop(client, registry)

    reply = loop.run("读取 test.txt")
    assert "hello" in reply
    assert loop.tool_call_count == 1
```

### 3. 多次工具调用

```python
def test_multiple_tool_calls():
    """模型连续调用多个工具"""
    client = mock_client_stream([
        {"text": "", "tool_use": [
            {"id": "t1", "name": "read", "input": {"path": "a.txt"}},
            {"id": "t2", "name": "read", "input": {"path": "b.txt"}},
        ]},
        {"text": "两个文件都读完了"},
    ])
    registry = ToolRegistry()
    registry.register(mock_read_tool())
    loop = AgentLoop(client, registry)

    reply = loop.run("读取 a.txt 和 b.txt")
    assert loop.tool_call_count == 2
```

### 4. 工具执行失败

```python
def test_tool_execution_error():
    """工具执行失败时，错误信息返回给模型"""
    client = mock_client_stream([
        {"text": "", "tool_use": {"id": "t1", "name": "read", "input": {"path": "missing.txt"}}},
        {"text": "文件不存在"},
    ])
    registry = ToolRegistry()
    registry.register(mock_read_tool(error="文件不存在"))
    loop = AgentLoop(client, registry)

    reply = loop.run("读取 missing.txt")
    assert "不存在" in reply
```

### 5. 最大轮次超限

```python
def test_max_turns_exceeded():
    """超过最大轮次时停止"""
    # 模型每次都调用工具，永不停止
    client = mock_client_stream([
        {"text": "", "tool_use": {"id": f"t{i}", "name": "noop", "input": {}}}
        for i in range(100)
    ])
    registry = ToolRegistry()
    registry.register(mock_noop_tool())
    loop = AgentLoop(client, registry, LoopConfig(max_turns=5))

    reply = loop.run("无限循环测试")
    assert "轮次" in reply or "turn" in reply.lower()
    assert loop.turn_count <= 5
```

### 6. 中断支持

```python
def test_abort():
    """可以中断正在执行的循环"""
    import threading

    client = mock_client_stream([
        {"text": "", "tool_use": {"id": "t1", "name": "slow", "input": {}}},
        {"text": "完成"},
    ])
    registry = ToolRegistry()
    registry.register(mock_slow_tool(delay=10))
    loop = AgentLoop(client, registry)

    def abort_after_delay():
        time.sleep(0.5)
        loop.abort()

    threading.Thread(target=abort_after_delay).start()

    with pytest.raises(KeyboardInterrupt):
        loop.run("慢操作")
```

### 7. 消息历史累积

```python
def test_message_history():
    """多轮对话保持消息历史"""
    client = mock_client(response="好的")
    registry = ToolRegistry()
    loop = AgentLoop(client, registry)

    loop.run("记住数字 42")
    loop.run("我让你记住什么？")

    # 验证消息历史包含之前的对话
    assert len(loop.messages) >= 4  # 2轮 × (user + assistant)
```

### 8. reset 清空历史

```python
def test_reset():
    """reset 清空消息历史"""
    client = mock_client(response="好的")
    registry = ToolRegistry()
    loop = AgentLoop(client, registry)

    loop.run("测试")
    assert len(loop.messages) > 0

    loop.reset()
    assert len(loop.messages) == 0
    assert loop.turn_count == 0
```

---

## 依赖

```
F03 Tool Protocol（必须）
F01 模型层（已有）
```

## 验收标准

- [ ] `LoopConfig` dataclass 在 `core/loop.py`
- [ ] `AgentLoop` class 在 `core/loop.py`
- [ ] `run()` 方法：完整循环（用户输入→模型→工具→结果→循环）
- [ ] `run_stream()` 方法：流式返回文本
- [ ] `_build_messages()` 构建正确的 API 消息格式
- [ ] `_build_system_prompt()` 组合系统提示
- [ ] `_parse_response()` 解析文本和 tool_use
- [ ] `_execute_tool_call()` 通过 registry 执行工具
- [ ] `_handle_tool_results()` 注入结果到消息历史
- [ ] `reset()` 清空历史
- [ ] `abort()` 中断执行
- [ ] 轮次超限保护
- [ ] 工具调用次数统计
- [ ] 测试覆盖所有场景
- [ ] `make check` 通过

## 面试可能问的问题

```
Q: 主循环的核心逻辑是什么？
A: 用户输入 → 构建消息 → 调用模型 → 解析响应 →
   有工具调用 → 执行工具 → 注入结果 → 循环
   无工具调用 → 返回给用户

Q: 为什么用 class 而不是函数？
A: 循环需要维护状态（消息历史、轮次计数、中断状态）。
   class 把这些状态封装在一起，接口更清晰。

Q: 如何防止无限循环？
A: 两个保护：
   1. max_turns: 最大轮次（默认 50）
   2. max_tool_calls: 最大工具调用次数（默认 100）
   超限时返回错误信息而不是崩溃。

Q: 工具执行失败怎么办？
A: 捕获异常，返回 ToolResult(is_error=True)。
   错误信息会作为 tool_result 注入消息历史，
   模型会看到错误并决定下一步（重试或换方案）。

Q: 如何处理用户中断（Ctrl+C）？
A: AbortController 模式：
   - 用户按 Ctrl+C 时调用 abort()
   - 工具执行前检查 is_aborted
   - 优雅退出而不是直接崩溃

Q: 消息格式是什么？
A: Anthropic API 格式：
   - user: {"role": "user", "content": "文本"}
   - assistant: {"role": "assistant", "content": "文本" 或 [...blocks]}
   - tool_result: {"role": "user", "content": [{type: "tool_result", ...}]}
```
