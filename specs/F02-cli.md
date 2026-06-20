# F02: CLI 框架 - 终端 UI

## 需求

用 rich 搭建终端 UI，实现类 Claude Code 的交互体验。

## 设计决策

### 为什么用 rich 而不是 print？

```
方案 A: print() 原生输出
  优点: 零依赖
  缺点: 没有颜色、没有 Markdown、没有表格、没有进度条

方案 B: rich（选择这个）
  优点: Markdown 渲染、语法高亮、面板、表格、进度条，开箱即用
  缺点: 额外依赖

选择理由: Python 生态里最成熟的终端渲染库。
```

### 流式输出的渲染策略

```
问题: 模型流式返回文本，什么时候渲染？

实际做法: 文本 chunk 先追加到缓冲区，
         遇到换行符时渲染上一段，
         收到结束信号时渲染剩余内容。
```

## Logo 设计

像素风格机器人 Logo：

```
  ▄▄▄
 █████
█ █ █ █
███████
 █   █
```

## 目标效果

```
╭─ Cool Code v0.1.0 ─────────────────────────╮
│                                              │
│   ▄▄▄                                        │
│  █████                                       │
│ █ █ █ █                                      │
│ ███████                                      │
│  █   █                                       │
│                                              │
│  Model: mimo-v2.5-pro                        │
│  CWD:   D:\Github\python-agent               │
│                                              │
╰──────────────────────────────────────────────╯

❯ 你好

  # 模型回复

  这是 Markdown 格式的回复...

  ┌─ file_read ──────────────────────────────┐
  │  path: test.py                            │
  └───────────────────────────────────────────┘
```

## 接口定义

```python
# cli/app.py

class AgentApp:
    """Cool Code 终端 UI"""

    def __init__(
        self,
        on_message: Callable[[str], Iterator[StreamEvent]],
        model: str = "mimo-v2.5-pro",
        version: str = "0.1.0",
    )

    def run(self) -> None                    # 主循环
    def show_header(self) -> None            # 显示 Header
    def show_welcome(self) -> None           # 欢迎信息
    def get_input(self) -> str               # 获取输入（❯ 提示符）
    def show_response(self, text: str) -> None  # Markdown 回复
    def render_stream_chunk(self, chunk: str) -> None  # 流式 chunk
    def flush_stream(self) -> None           # 渲染剩余
    def show_tool_call(self, name: str, args: dict) -> None  # 工具面板
    def show_tool_result(self, output: str, is_error: bool) -> None  # 工具结果
    def show_error(self, message: str) -> None  # 错误
    def show_status(self, text: str) -> None  # 状态栏


# 便捷入口
def start_cli_session(on_message: Callable[[str], Iterator[StreamEvent]]) -> None
```

## 测试场景

1. 初始化（默认、自定义参数）
2. Header 显示（Panel 渲染）
3. 输入处理（正常、Ctrl+C、Ctrl+D）
4. 命令处理（/help, /clear, /reset, /exit, /quit）
5. 流式缓冲（chunk 缓冲、换行渲染、flush）
6. 工具面板（调用显示、结果截断）
7. 错误渲染
8. 事件分发（text/tool_call/tool_result）
9. 主循环（退出、中断、空输入、回调调用、回调异常）

## 验收标准

- [x] Logo 为像素风格机器人
- [x] 品牌色 rgb(215,119,87)
- [x] round 边框 Header
- [x] ❯ 提示符
- [x] Markdown 渲染
- [x] 工具调用面板
- [x] 长输出截断
- [x] 测试覆盖各场景
- [x] `make check` 通过

## 面试可能问的问题

```
Q: 流式输出怎么做到不闪烁的？
A: 用缓冲策略，chunk 先攒着，遇到换行再渲染。

Q: 为什么选 rich？
A: Python 生态最成熟的终端渲染库，开箱即用支持 Markdown、面板、表格。

Q: Logo 为什么用 Unicode 字符？
A: 现代终端都支持 Unicode，像素风格有辨识度，比纯 ASCII 更有设计感。
```

## 文件结构

```
src/agent/cli/
├── __init__.py    # 导出 AgentApp, start_cli_session
└── app.py         # AgentApp 实现
```

## 依赖

```toml
"rich>=13.0.0",  # 终端渲染
```
