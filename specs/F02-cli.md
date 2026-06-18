# F02: CLI 框架 - 终端 UI

## 需求

用 rich + prompt_toolkit 搭建终端 UI，实现：
- 输入框（带提示符）
- Markdown 渲染（标题、列表、粗体）
- 代码块语法高亮
- 流式输出（打字机效果）
- 工具调用面板

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
from prompt_toolkit import PromptSession

class AgentApp:
    """终端 UI 应用"""

    def __init__(self):
        self.console = Console()
        self.session = PromptSession()

    def run(self):
        """启动交互循环"""
        self.show_welcome()
        while True:
            user_input = self.get_input()
            if user_input.strip() == "/exit":
                break
            self.handle_input(user_input)

    def show_welcome(self):
        """显示欢迎信息"""
        ...

    def get_input(self) -> str:
        """获取用户输入"""
        ...

    def render_markdown(self, text: str):
        """渲染 Markdown 文本"""
        ...

    def render_tool_call(self, name: str, args: dict):
        """渲染工具调用面板"""
        ...

    def render_tool_result(self, output: str, is_error: bool):
        """渲染工具执行结果"""
        ...

    def render_stream_chunk(self, chunk: str):
        """渲染流式输出的一块文本"""
        ...
```

## 依赖

```toml
"rich>=13.0",           # 终端渲染
"prompt-toolkit>=3.0",  # 输入交互
"pygments>=2.0",        # 代码高亮（rich 依赖）
```

## 测试场景

### 1. Markdown 渲染

```python
def test_render_markdown_heading():
    """能渲染 Markdown 标题"""
    app = AgentApp()
    # 不崩溃，输出包含标题文本
    app.render_markdown("# Hello")
```

### 2. 代码块高亮

```python
def test_render_code_block():
    """能渲染带语法高亮的代码块"""
    app = AgentApp()
    app.render_markdown("```python\nprint('hi')\n```")
```

### 3. 工具面板

```python
def test_render_tool_call():
    """能渲染工具调用面板"""
    app = AgentApp()
    app.render_tool_call("file_read", {"path": "test.py"})
```

### 4. 流式输出

```python
def test_render_stream():
    """流式输出能逐块显示"""
    app = AgentApp()
    for chunk in ["Hello", " World", "!"]:
        app.render_stream_chunk(chunk)
```

## 验收标准

- [ ] `AgentApp` 定义在 `cli/app.py`
- [ ] 有输入框，能获取用户输入
- [ ] 能渲染 Markdown（标题、粗体、列表）
- [ ] 能渲染代码块（带语法高亮）
- [ ] 能渲染工具调用面板
- [ ] 支持流式输出
- [ ] `/exit` 退出
- [ ] `make check` 通过
