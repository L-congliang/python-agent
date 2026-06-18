# F02: CLI 框架 - 终端 UI

## 需求

用 rich + prompt_toolkit 搭建终端 UI，实现类 Claude Code 的交互体验。
不是"能输入输出就行"，而是要处理各种边界情况和用户体验细节。

## 设计决策

### 为什么用 rich 而不是 print？

```
方案 A: print() 原生输出
  优点: 零依赖
  缺点: 没有颜色、没有 Markdown、没有表格、没有进度条

方案 B: rich（选择这个）
  优点: Markdown 渲染、语法高亮、面板、表格、进度条，开箱即用
  缺点: 额外依赖

选择理由: Claude Code 的核心体验就是"终端里的富文本渲染"，
          rich 是 Python 生态里最成熟的方案。
```

### 为什么用 prompt_toolkit 而不是 input()？

```
方案 A: input()
  优点: 零依赖
  缺点: 没有历史记录、没有补全、没有快捷键、没有多行输入

方案 B: prompt_toolkit（选择这个）
  优点: 历史记录、快捷键、多行输入、语法高亮输入
  缺点: 额外依赖

选择理由: prompt_toolkit 是 Python 终端交互的标准库，
          IPython、pgcli 等知名项目都用它。
```

### 流式输出的渲染策略

```
问题: 模型流式返回文本，什么时候渲染？

方案 A: 每个 chunk 立即渲染
  优点: 延迟最低
  缺点: Markdown 渲染会闪烁（标题还没收完时渲染不完整）

方案 B: 攒够一个段落再渲染（选择这个）
  优点: 渲染质量高
  缺点: 略有延迟

方案 C: 先纯文本显示，收完后再用 Markdown 重新渲染
  优点: 实时 + 质量
  缺点: 屏幕会闪

实际做法: 文本 chunk 先追加到缓冲区，
         遇到换行符时渲染上一段，
         收到结束信号时渲染剩余内容。
```

## 目标效果

```
╭─ mimo agent ─────────────────────────────────╮
│                                               │
│  > 帮我写一个 hello world                      │
│                                               │
│  好的，我来创建一个 Python 文件：                │
│                                               │
│  ┌─ file_write ────────────────────────────┐  │
│  │  path: hello.py                          │  │
│  └──────────────────────────────────────────┘  │
│                                               │
│  ```python                                   │
│  print("Hello, World!")                      │
│  ```                                          │
│                                               │
│  文件已创建。                                  │
│                                               │
│  > _                                          │
╰───────────────────────────────────────────────╯
```

## 接口定义

```python
# cli/app.py

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory


class AgentApp:
    """终端 UI 应用

    职责:
    - 管理输入交互（prompt_toolkit）
    - 渲染输出（rich）
    - 处理流式输出的缓冲和渲染
    - 处理键盘事件（Ctrl+C, Ctrl+D）
    """

    def __init__(self, on_message: Callable[[str], None]):
        """
        Args:
            on_message: 用户输入消息后的回调，由外部（主循环）提供
        """
        self.console = Console()
        self.session = PromptSession(history=InMemoryHistory())
        self.on_message = on_message
        self._stream_buffer = ""  # 流式输出缓冲区

    def run(self) -> None:
        """启动交互循环，阻塞直到用户退出"""
        self._show_welcome()
        while True:
            try:
                user_input = self._get_input()
                if user_input.strip() in ("/exit", "/quit"):
                    self._show_goodbye()
                    break
                if not user_input.strip():
                    continue
                self.on_message(user_input)
            except KeyboardInterrupt:
                continue  # Ctrl+C 取消当前输入
            except EOFError:
                break      # Ctrl+D 退出

    def render_assistant_text(self, text: str) -> None:
        """渲染助手的完整文本回复（Markdown）"""
        ...

    def render_stream_chunk(self, chunk: str) -> None:
        """渲染流式输出的一个 chunk

        策略：追加到缓冲区，遇到换行符时渲染上一段
        """
        ...

    def flush_stream(self) -> None:
        """流式结束时，渲染缓冲区剩余内容"""
        ...

    def render_tool_call(self, name: str, args: dict) -> None:
        """渲染工具调用面板

        显示：工具名称、参数（格式化）
        """
        ...

    def render_tool_result(self, output: str, is_error: bool = False) -> None:
        """渲染工具执行结果

        正常结果：折叠显示（超过 N 行时截断）
        错误结果：红色高亮显示
        """
        ...

    def render_error(self, message: str) -> None:
        """渲染错误信息"""
        ...

    def _show_welcome(self) -> None:
        """显示欢迎信息和使用说明"""
        ...

    def _show_goodbye(self) -> None:
        """显示退出信息"""
        ...

    def _get_input(self) -> str:
        """获取用户输入

        支持：
        - 上下箭头翻历史
        - Ctrl+C 取消
        - Ctrl+D 退出
        """
        ...
```

## 关键实现细节

### 流式渲染缓冲策略

```python
def render_stream_chunk(self, chunk: str) -> None:
    self._stream_buffer += chunk
    # 遇到换行符时，渲染之前的内容
    while "\n" in self._stream_buffer:
        line, self._stream_buffer = self._stream_buffer.split("\n", 1)
        self.console.print(Markdown(line))

def flush_stream(self) -> None:
    if self._stream_buffer.strip():
        self.console.print(Markdown(self._stream_buffer))
    self._stream_buffer = ""
```

### 工具结果截断

```python
MAX_OUTPUT_LINES = 50

def render_tool_result(self, output: str, is_error: bool = False) -> None:
    lines = output.split("\n")
    if len(lines) > MAX_OUTPUT_LINES:
        truncated = "\n".join(lines[:MAX_OUTPUT_LINES])
        truncated += f"\n... ({len(lines) - MAX_OUTPUT_LINES} more lines)"
    else:
        truncated = output

    style = "red" if is_error else "dim"
    self.console.print(Panel(truncated, style=style))
```

### 键盘事件处理

```python
def _get_input(self) -> str:
    try:
        return self.session.prompt(
            "> ",
            multiline=False,
            wrap_lines=True,
        )
    except KeyboardInterrupt:
        raise  # 由外层 run() 捕获
    except EOFError:
        raise  # 由外层 run() 捕获
```

## 测试场景

### 1. 启动和退出

```python
def test_run_exits_on_exit_command():
    """输入 /exit 时正常退出"""
    # mock 输入为 ["/exit"]
    app = AgentApp(on_message=lambda x: None)
    # 验证不崩溃，正常退出
```

### 2. Markdown 渲染

```python
def test_render_heading():
    """能渲染 Markdown 标题"""
    app = AgentApp(on_message=lambda x: None)
    app.render_assistant_text("# Hello World")
    # 验证 console.print 被调用，参数是 Markdown 对象

def test_render_code_block():
    """能渲染代码块（带语法高亮）"""
    app = AgentApp(on_message=lambda x: None)
    app.render_assistant_text("```python\nprint('hi')\n```")
```

### 3. 流式输出

```python
def test_stream_chunks_buffered():
    """流式 chunk 先缓冲，换行时渲染"""
    app = AgentApp(on_message=lambda x: None)
    app.render_stream_chunk("Hello")
    app.render_stream_chunk(" World\n")
    # "Hello World" 应该被渲染
    app.render_stream_chunk("Next line")
    app.flush_stream()
    # "Next line" 在 flush 时渲染
```

### 4. 工具面板

```python
def test_tool_call_panel():
    """工具调用显示为面板"""
    app = AgentApp(on_message=lambda x: None)
    app.render_tool_call("file_read", {"path": "test.py"})
    # 验证 Panel 被创建，包含工具名和参数
```

### 5. 长输出截断

```python
def test_long_output_truncated():
    """超过 50 行的输出被截断"""
    app = AgentApp(on_message=lambda x: None)
    long_output = "\n".join([f"line {i}" for i in range(100)])
    app.render_tool_result(long_output)
    # 验证显示 "... (50 more lines)"
```

### 6. 快捷键

```python
def test_ctrl_c_does_not_exit():
    """Ctrl+C 取消当前输入，不退出程序"""
    ...

def test_ctrl_d_exits():
    """Ctrl+D 退出程序"""
    ...
```

## 依赖

```toml
"rich>=13.0.0",           # 终端渲染
"prompt-toolkit>=3.0.0",  # 输入交互
```

## 文件结构

```
src/agent/cli/
├── __init__.py
└── app.py          ← AgentApp
```

## 验收标准

- [ ] `AgentApp` 定义在 `cli/app.py`
- [ ] 输入框支持上下箭头翻历史
- [ ] Ctrl+C 取消当前输入，不退出
- [ ] Ctrl+D 正常退出
- [ ] Markdown 渲染：标题、粗体、列表
- [ ] 代码块语法高亮
- [ ] 流式输出：缓冲策略，不闪烁
- [ ] 工具调用面板：显示名称和参数
- [ ] 长输出截断：超过 50 行时折叠
- [ ] 错误信息红色高亮
- [ ] 测试覆盖各场景
- [ ] `make check` 通过

## 面试可能问的问题

```
Q: 流式输出怎么做到不闪烁的？
A: 用缓冲策略，chunk 先攒着，遇到换行再渲染。
   直接每个 chunk 渲染会导致 Markdown 解析不完整。

Q: 为什么选 prompt_toolkit 而不是 input()？
A: input() 没有历史记录、快捷键、多行输入。
   prompt_toolkit 是 IPython 同款，成熟可靠。

Q: 长输出怎么处理？
A: 超过 50 行截断，显示 "... (N more lines)"。
   用户可以要求模型分段输出。

Q: 终端宽度怎么适配？
A: rich 的 Console 自动检测终端宽度，Panel 和 Markdown 会自动换行。
```
