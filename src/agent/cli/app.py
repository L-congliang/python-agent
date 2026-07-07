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
import sys
from collections.abc import Callable, Iterator
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from agent.core.types import (
    ObservationMetadata,
    PermissionConfirmationOutcome,
    PermissionRequest,
    StreamEvent,
)

# ============================================================
# 主题颜色
# ============================================================

BRAND_COLOR = "rgb(215,119,87)"  # 品牌橙色
TEXT_WHITE = "rgb(255,255,255)"  # 主文字
INACTIVE_GRAY = "rgb(153,153,153)"  # 次要文字

# 工具结果截断阈值
MAX_OUTPUT_LINES = 50
MAX_CONFIRM_PREVIEW_LINES = 40

# ============================================================
# Logo（机器人像素风格）
# ============================================================

LOGO = """  ▄▄▄
 █████
█ █ █ █
███████
 █   █"""
ASCII_LOGO = "  [ Cool Code ]"


def _supports_text(text: str, encoding: str | None) -> bool:
    """判断当前终端编码是否支持给定文本。"""
    if not encoding:
        return True
    if sys.platform == "win32" and "utf" not in encoding.lower():
        return False
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        return False
    return True


def get_logo_lines(use_ascii: bool = False) -> list[str]:
    """获取 Logo 的行数据"""
    logo = ASCII_LOGO if use_ascii else LOGO
    return logo.strip().split("\n")


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
        on_reset: Callable[[], None] | None = None,
        on_rollback: Callable[[], tuple[bool, str]] | None = None,
        on_history: Callable[[], list[Any]] | None = None,
        model: str = "mimo-v2.5-pro",
        version: str = "0.1.0",
    ) -> None:
        """初始化 CLI 应用

        Args:
            on_message: 用户输入消息后的回调，返回事件流
            on_compact: 压缩命令的回调，返回 (压缩前消息数, 压缩后消息数)
            on_rollback: 回退命令的回调，返回 (success, message)
            on_history: 历史命令的回调，返回历史记录列表
            model: 模型名称
            version: 版本号
        """
        self.console = Console()
        self.on_message = on_message
        self.on_compact = on_compact
        self.on_reset = on_reset
        self.on_rollback = on_rollback
        self.on_history = on_history
        self.model = model
        self.version = version
        self._stream_buffer: str = ""
        self._last_confirmation_scope: str = "once"  # 用于传递 allow-once / allow-session
        encoding = getattr(self.console.file, "encoding", None)
        self._use_ascii_ui = not _supports_text(LOGO, encoding)
        self._prompt_symbol = ">" if self._use_ascii_ui else "❯"
        self._welcome_symbol = "*" if self._use_ascii_ui else "✨"

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
        logo_lines = get_logo_lines(use_ascii=self._use_ascii_ui)
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
            f"\n  [{BRAND_COLOR}]{self._welcome_symbol}[/] "
            f"[bold]Welcome to Cool Code[/bold] "
            f"[{INACTIVE_GRAY}]v{self.version}[/]\n"
        )

    def get_input(self) -> str:
        """获取用户输入（带 ❯ 提示符）

        Returns:
            用户输入的文本
        """
        try:
            return self.console.input(f"\n[{BRAND_COLOR}]{self._prompt_symbol}[/] ")
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

    def show_tool_result(
        self,
        output: str,
        is_error: bool = False,
        observation: ObservationMetadata | None = None,
    ) -> None:
        """显示工具执行结果

        Args:
            output: 工具输出
            is_error: 是否出错
            observation: 观察元数据（可选，用于显示截断提示）
        """
        # 如果有 observation 且被截断，使用 preview
        if observation is not None and observation.was_truncated:
            display_output = observation.preview or output
        else:
            display_output = output

        lines = display_output.split("\n")

        if len(lines) > MAX_OUTPUT_LINES:
            truncated = "\n".join(lines[:MAX_OUTPUT_LINES])
            truncated += f"\n... ({len(lines) - MAX_OUTPUT_LINES} more lines)"
        else:
            truncated = display_output

        border_style = "red" if is_error else INACTIVE_GRAY
        style = "red" if is_error else ""

        panel = Panel(
            truncated,
            style=style,
            border_style=border_style,
            padding=(0, 1),
        )
        self.console.print(panel)

        # 显示 observation 元信息（截断提示 + artifact 路径）
        if observation is not None and observation.was_truncated:
            self._show_observation_hint(observation)

    def _show_observation_hint(self, observation: ObservationMetadata) -> None:
        """显示 observation 元信息（截断提示 + artifact 路径）

        Args:
            observation: 观察元数据
        """
        hint_parts = []

        if observation.full_output_chars > 0:
            hint_parts.append(f"输出已截断（完整内容 {observation.full_output_chars} 字符）")

        if observation.artifact_path:
            hint_parts.append(f"完整结果已保存到: {observation.artifact_path}")

        if hint_parts:
            hint_text = " | ".join(hint_parts)
            self.console.print(f"  [dim]{hint_text}[/dim]")

    def _is_interactive_confirmation_available(self) -> bool:
        """判断当前 CLI 是否可进行交互确认。"""
        stream = getattr(self.console, "file", None)
        if stream is None or not hasattr(stream, "isatty"):
            return False
        try:
            return bool(stream.isatty())
        except Exception:
            return False

    def _truncate_preview(self, preview: str) -> str:
        """截断确认预览，避免在终端刷屏。"""
        lines = preview.splitlines()
        if len(lines) <= MAX_CONFIRM_PREVIEW_LINES:
            return preview
        head = "\n".join(lines[:MAX_CONFIRM_PREVIEW_LINES])
        return f"{head}\n... ({len(lines) - MAX_CONFIRM_PREVIEW_LINES} more lines)"

    def confirm_permission(
        self,
        request: PermissionRequest,
    ) -> PermissionConfirmationOutcome:
        """在 CLI 中向用户确认高风险工具调用。"""
        if not self._is_interactive_confirmation_available():
            return PermissionConfirmationOutcome.UNAVAILABLE

        content = Text()
        content.append(f"{request.message}\n", style="bold")

        if request.tool_name == "bash":
            command = str(request.tool_input.get("command", "")).strip()
            if command:
                content.append("命令: ", style=INACTIVE_GRAY)
                content.append(f"{command}\n")
        elif request.tool_name in ("write", "edit"):
            file_path = str(request.tool_input.get("file_path", "")).strip()
            if file_path:
                content.append("文件: ", style=INACTIVE_GRAY)
                content.append(f"{file_path}\n")

        if request.preview:
            content.append("\n预览:\n", style=INACTIVE_GRAY)
            content.append(self._truncate_preview(request.preview))

        panel = Panel(
            content,
            title=f"[bold {BRAND_COLOR}]需要确认: {request.tool_name}[/]",
            border_style="yellow",
            padding=(0, 1),
        )
        self.console.print(panel)

        answer = self.console.input(
            f"[yellow]是否允许执行？[/yellow] [{BRAND_COLOR}]y[/] / [{BRAND_COLOR}]a[/]llow session / [red]N[/] (默认 N): "
        ).strip().lower()

        if answer in {"y", "yes"}:
            return PermissionConfirmationOutcome.APPROVED
        if answer in {"a", "allow"}:
            # 返回 APPROVED，但通过 _last_confirmation_scope 传递 scope
            self._last_confirmation_scope = "session"
            return PermissionConfirmationOutcome.APPROVED
        return PermissionConfirmationOutcome.DENIED

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
                event.observation,
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
  /help      - 显示此帮助
  /clear     - 清屏
  /reset     - 重置对话历史
  /compact   - 压缩上下文历史
  /history   - 显示编辑历史
  /rollback  - 回退最近一次修改
  /exit      - 退出程序
  /quit      - 退出程序

[{INACTIVE_GRAY}]快捷键:[/]
  Ctrl+C  - 取消当前输入
  Ctrl+D  - 退出程序
""")
            return True

        if cmd == "/clear":
            self.console.clear()
            return True

        if cmd == "/reset":
            if self.on_reset:
                self.on_reset()
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

        if cmd == "/history":
            if self.on_history:
                try:
                    records = self.on_history()
                    if not records:
                        self.console.print("[yellow]没有编辑历史[/yellow]")
                    else:
                        self.console.print(f"[bold {BRAND_COLOR}]编辑历史:[/]")
                        for i, record in enumerate(records[-10:], 1):  # 只显示最近 10 条
                            action = record.action
                            tool = record.tool_name
                            path = os.path.basename(record.file_path)
                            self.console.print(f"  {i}. [{action}] {tool} {path}")
                except Exception as e:
                    self.console.print(f"[red]获取历史失败: {e}[/red]")
            else:
                self.console.print("[yellow]历史功能未启用[/yellow]")
            return True

        if cmd.startswith("/rollback"):
            if self.on_rollback:
                try:
                    success, msg = self.on_rollback()
                    if success:
                        self.console.print(f"[green]{msg}[/green]")
                    else:
                        self.console.print(f"[yellow]{msg}[/yellow]")
                except Exception as e:
                    self.console.print(f"[red]回退失败: {e}[/red]")
            else:
                self.console.print("[yellow]回退功能未启用[/yellow]")
            return True

        return False


# ============================================================
# 便捷入口
# ============================================================


def start_cli_session(
    on_message: Callable[[str], Iterator[StreamEvent]],
    on_compact: Callable[[], tuple[int, int]] | None = None,
    on_reset: Callable[[], None] | None = None,
) -> None:
    """启动 CLI 会话

    Args:
        on_message: 消息回调
    """
    app = AgentApp(
        on_message=on_message,
        on_compact=on_compact,
        on_reset=on_reset,
    )
    app.run()
