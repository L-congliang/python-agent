"""CLI 应用 - Cool Code 终端 UI

Cool Code 的视觉体验：
- 机器人 Logo（像素风格）
- 橙色主题 rgb(215,119,87)
- round 边框 Header
- ❯ 提示符
- 底部状态栏

设计决策:
- 为什么用 rich？Python 生态最成熟的终端渲染库
- 为什么不用 prompt_toolkit？rich 的 input() 够用，减少依赖
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from agent.core.types import StreamEvent

# ============================================================
# 主题颜色
# ============================================================

BRAND_COLOR = "rgb(215,119,87)"  # 品牌橙色
TEXT_WHITE = "rgb(255,255,255)"  # 主文字
INACTIVE_GRAY = "rgb(153,153,153)"  # 次要文字

# 工具结果截断阈值
MAX_OUTPUT_LINES = 50

# ============================================================
# Logo（机器人像素风格）
# ============================================================

LOGO = """  ▄▄▄
 █████
█ █ █ █
███████
 █   █"""


def get_logo_lines() -> list[str]:
    """获取 Logo 的行数据"""
    return LOGO.strip().split("\n")


# ============================================================
# AgentApp 主类
# ============================================================


class AgentApp:
    """Cool Code 终端 UI

    职责:
    - 显示 Header（Logo + 信息 + 边框）
    - 渲染 Markdown 回复
    - 显示工具调用面板
    - 底部状态栏

    使用方式:
        def handle_message(msg: str) -> Iterator[StreamEvent]:
            return agent_loop.run_stream(msg)

        app = AgentApp(on_message=handle_message)
        app.run()
    """

    def __init__(
        self,
        on_message: Callable[[str], Iterator[StreamEvent]],
        on_compact: Callable[[], tuple[int, int]] | None = None,
        model: str = "mimo-v2.5-pro",
        version: str = "0.1.0",
    ) -> None:
        """初始化 CLI 应用

        Args:
            on_message: 用户输入消息后的回调，返回事件流
            on_compact: 压缩命令的回调，返回 (压缩前消息数, 压缩后消息数)
            model: 模型名称
            version: 版本号
        """
        self.console = Console()
        self.on_message = on_message
        self.on_compact = on_compact
        self.model = model
        self.version = version
        self._stream_buffer: str = ""

    def run(self) -> None:
        """启动交互循环"""
        self.show_header()
        self.console.print()

        while True:
            try:
                user_input = self.get_input()

                if user_input.startswith("/"):
                    if self._handle_command(user_input):
                        continue

                if not user_input.strip():
                    continue

                # 调用回调，消费事件流
                try:
                    for event in self.on_message(user_input):
                        self._handle_event(event)
                except KeyboardInterrupt:
                    self.console.print("\n[yellow]已中断[/yellow]")
                except Exception as e:
                    self.show_error(str(e))

                self.console.print()  # 回复后空行

            except KeyboardInterrupt:
                continue
            except EOFError:
                break

        self.console.print("\n[dim]再见！[/dim]")

    def show_header(self) -> None:
        """显示 Header（Logo + 信息 + round 边框）"""
        cwd = os.getcwd()
        # 截断路径，保留最后 40 字符
        if len(cwd) > 40:
            cwd = "..." + cwd[-37:]

        # 构建内容
        content = Text()

        # Logo
        logo_lines = get_logo_lines()
        for line in logo_lines:
            content.append(f"  {line}\n", style=f"bold {BRAND_COLOR}")

        # 空行
        content.append("\n")

        # 模型信息
        content.append(f"  Model: ", style=INACTIVE_GRAY)
        content.append(f"{self.model}\n", style="bold")
        content.append(f"  CWD:   ", style=INACTIVE_GRAY)
        content.append(f"{cwd}\n", style="bold")

        # 边框标题
        border_title = f" Cool Code v{self.version} "

        panel = Panel(
            content,
            border_style=BRAND_COLOR,
            title=border_title,
            title_align="left",
            padding=(1, 2),
        )
        self.console.print(panel)

    def show_welcome(self) -> None:
        """显示欢迎信息（简化版）"""
        self.console.print(
            f"\n  [{BRAND_COLOR}]✦[/] "
            f"[bold]Welcome to Cool Code[/bold] "
            f"[{INACTIVE_GRAY}]v{self.version}[/]\n"
        )

    def get_input(self) -> str:
        """获取用户输入（带 ❯ 提示符）

        Returns:
            用户输入的文本
        """
        try:
            return self.console.input(f"\n[{BRAND_COLOR}]❯[/] ")
        except KeyboardInterrupt:
            raise
        except EOFError:
            raise

    def show_response(self, text: str) -> None:
        """显示模型回复（Markdown 渲染）

        Args:
            text: Markdown 格式的文本
        """
        self.console.print(Markdown(text))

    def render_stream_chunk(self, chunk: str) -> None:
        """渲染流式输出 chunk

        策略：攒到缓冲区，遇换行渲染。

        Args:
            chunk: 文本片段
        """
        self._stream_buffer += chunk

        while "\n" in self._stream_buffer:
            line, self._stream_buffer = self._stream_buffer.split("\n", 1)
            if line.strip():
                self.console.print(Markdown(line))
            else:
                self.console.print()

    def flush_stream(self) -> None:
        """渲染缓冲区剩余内容"""
        if self._stream_buffer.strip():
            self.console.print(Markdown(self._stream_buffer))
        self._stream_buffer = ""

    def show_tool_call(self, name: str, args: dict[str, Any]) -> None:
        """显示工具调用面板

        Args:
            name: 工具名称
            args: 工具参数
        """
        args_text = Text()
        for key, value in args.items():
            args_text.append(f"  {key}: ", style=INACTIVE_GRAY)
            args_text.append(f"{value}\n")

        panel = Panel(
            args_text,
            title=f"[bold {BRAND_COLOR}]{name}[/]",
            border_style=BRAND_COLOR,
            padding=(0, 1),
        )
        self.console.print(panel)

    def show_tool_result(self, output: str, is_error: bool = False) -> None:
        """显示工具执行结果

        Args:
            output: 工具输出
            is_error: 是否出错
        """
        lines = output.split("\n")

        if len(lines) > MAX_OUTPUT_LINES:
            truncated = "\n".join(lines[:MAX_OUTPUT_LINES])
            truncated += f"\n... ({len(lines) - MAX_OUTPUT_LINES} more lines)"
        else:
            truncated = output

        border_style = "red" if is_error else INACTIVE_GRAY
        style = "red" if is_error else ""

        panel = Panel(
            truncated,
            style=style,
            border_style=border_style,
            padding=(0, 1),
        )
        self.console.print(panel)

    def show_error(self, message: str) -> None:
        """显示错误信息

        Args:
            message: 错误信息
        """
        self.console.print(f"[bold red]错误:[/bold red] {message}")

    def show_status(self, text: str) -> None:
        """显示底部状态栏

        Args:
            text: 状态文本
        """
        self.console.print(f"\n[{INACTIVE_GRAY}]{text}[/]")

    def _handle_event(self, event: StreamEvent) -> None:
        """事件分发

        Args:
            event: 流式事件
        """
        if event.type == "text":
            self.render_stream_chunk(event.content or "")
        elif event.type == "tool_call":
            self.flush_stream()
            self.show_tool_call(
                event.tool_name or "unknown",
                event.tool_input or {},
            )
        elif event.type == "tool_result":
            self.show_tool_result(
                str(event.content) if event.content else "",
                event.is_error,
            )

    def _handle_command(self, cmd: str) -> bool:
        """处理命令

        Args:
            cmd: 命令字符串

        Returns:
            True 表示已处理
        """
        cmd = cmd.strip().lower()

        if cmd in ("/exit", "/quit"):
            raise EOFError("用户退出")

        if cmd == "/help":
            self.console.print(f"""
[bold {BRAND_COLOR}]可用命令:[/]
  /help    - 显示此帮助
  /clear   - 清屏
  /reset   - 重置对话历史
  /compact - 压缩上下文历史
  /exit    - 退出程序
  /quit    - 退出程序

[{INACTIVE_GRAY}]快捷键:[/]
  Ctrl+C  - 取消当前输入
  Ctrl+D  - 退出程序
""")
            return True

        if cmd == "/clear":
            self.console.clear()
            return True

        if cmd == "/reset":
            self.console.print("[yellow]对话已重置[/yellow]")
            return True

        if cmd == "/compact":
            if self.on_compact:
                try:
                    before, after = self.on_compact()
                    if before == 0:
                        self.console.print("[yellow]没有消息需要压缩[/yellow]")
                    else:
                        self.console.print(f"[green]压缩完成: {before} -> {after} 条消息[/green]")
                except Exception as e:
                    self.console.print(f"[red]压缩失败: {e}[/red]")
            else:
                self.console.print("[yellow]压缩功能未启用[/yellow]")
            return True

        return False


# ============================================================
# 便捷入口
# ============================================================


def start_cli_session(on_message: Callable[[str], Iterator[StreamEvent]]) -> None:
    """启动 CLI 会话

    Args:
        on_message: 消息回调
    """
    app = AgentApp(on_message=on_message)
    app.run()
