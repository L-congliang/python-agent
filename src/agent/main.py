"""Cool Code 入口

MimoClient → AgentLoop → AgentApp

使用方式:
    python -m agent.main
"""

import sys
import logging
import os
from collections.abc import Iterator
from typing import Callable

from agent.core.model import MimoClient, load_config
from agent.core.loop import AgentLoop, LoopConfig
from agent.tools.registry import ToolRegistry, register_base_tools
from agent.cli.app import AgentApp
from agent.core.types import StreamEvent, ToolCall, ToolResult


def setup_logging(debug: bool = False) -> None:
    """配置日志"""
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(name)s: %(message)s",
        stream=sys.stderr,
    )


def create_default_registry() -> ToolRegistry:
    """创建默认基础工具注册表。"""
    return register_base_tools(ToolRegistry())


def create_agent_loop(
    client: MimoClient,
    *,
    model: str,
    workspace_root: str | None = None,
    registry: ToolRegistry | None = None,
    artifact_dir: str | None = None,
    edit_history_dir: str | None = None,
    session_dir: str | None = None,
) -> AgentLoop:
    """创建默认 AgentLoop。"""
    resolved_workspace_root = workspace_root or os.getcwd()
    # 默认 artifact 目录：workspace/.artifacts
    resolved_artifact_dir = artifact_dir or os.path.join(resolved_workspace_root, ".artifacts")
    # 默认 edit history 目录：workspace/.agent/file-history
    resolved_edit_history_dir = edit_history_dir or os.path.join(resolved_workspace_root, ".agent", "file-history")
    # 默认 session 目录：workspace/.agent/sessions
    resolved_session_dir = session_dir or os.path.join(resolved_workspace_root, ".agent", "sessions")
    return AgentLoop(
        client,
        registry or create_default_registry(),
        config=LoopConfig(
            model=model,
            workspace_root=resolved_workspace_root,
            artifact_dir=resolved_artifact_dir,
            edit_history_dir=resolved_edit_history_dir,
            session_dir=resolved_session_dir,
        ),
    )


def create_message_handler(loop: AgentLoop) -> Callable[[str], Iterator[StreamEvent]]:
    """创建 CLI 使用的消息回调。"""
    # 用于收集 tool_result 事件的队列
    _tool_result_events: list[StreamEvent] = []

    # 保留已有的 on_tool_result 回调（callback chaining）
    _existing_on_tool_result = loop._config.on_tool_result

    def _on_tool_result(tool_call: ToolCall, result: ToolResult) -> None:
        """工具执行完成回调，将结果转换为 StreamEvent"""
        # 先调用已有的回调（如果有）
        if _existing_on_tool_result:
            _existing_on_tool_result(tool_call, result)

        # 再入队 CLI 事件
        _tool_result_events.append(StreamEvent(
            type="tool_result",
            content=result.output,
            tool_name=tool_call.name,
            tool_input=tool_call.arguments,
            is_error=result.is_error,
            observation=result.observation,
        ))

    # 注册回调（保留旧回调的 chaining）
    loop._config.on_tool_result = _on_tool_result

    def handle_message(msg: str) -> Iterator[StreamEvent]:
        # 清空事件队列
        _tool_result_events.clear()

        # 启动流式输出
        stream_iter = loop.run_stream(msg)

        # 交替 yield 文本 chunk 和 tool_result 事件
        for chunk in stream_iter:
            yield StreamEvent(type="text", content=chunk)

            # yield 所有待处理的 tool_result 事件
            while _tool_result_events:
                yield _tool_result_events.pop(0)

        # 尾部 flush：流结束后，yield 所有剩余的 tool_result 事件
        while _tool_result_events:
            yield _tool_result_events.pop(0)

    return handle_message


def create_agent_app(loop: AgentLoop, *, model: str) -> AgentApp:
    """创建默认 CLI app，并接好 loop 回调。"""
    # 创建 rollback 和 history 回调
    def _on_rollback() -> tuple[bool, str]:
        """回退最近一次修改"""
        if loop._edit_history_store is None:
            return False, "历史记录功能未启用"
        return loop._edit_history_store.rollback_latest()

    def _on_history() -> list:
        """获取编辑历史"""
        if loop._edit_history_store is None:
            return []
        return loop._edit_history_store.get_all()

    def _on_session() -> dict | None:
        """获取当前 session 摘要"""
        return loop.get_session_summary()

    def _on_sessions() -> list:
        """列出最近 sessions"""
        return loop.list_recent_sessions()

    def _on_inspect() -> dict:
        """获取 inspect 摘要"""
        return loop.get_inspect_summary()

    app = AgentApp(
        on_message=create_message_handler(loop),
        on_compact=loop.compact,
        on_reset=loop.reset,
        on_rollback=_on_rollback,
        on_history=_on_history,
        on_session=_on_session,
        on_sessions=_on_sessions,
        on_inspect=_on_inspect,
        model=model,
    )
    loop.set_permission_handler(app.confirm_permission)
    return app


def main() -> None:
    """主入口"""
    import argparse
    import sys

    # 只在直接运行时解析参数，不在 pytest 环境下解析
    if hasattr(sys, '_getframe') and 'pytest' in sys.modules:
        args = argparse.Namespace(resume=None)
    else:
        parser = argparse.ArgumentParser(description="Python Code Agent")
        parser.add_argument(
            "--resume",
            type=str,
            default=None,
            help="恢复 session：latest 或 session_id",
        )
        args = parser.parse_args()

    setup_logging(debug=False)

    # 1. 加载配置
    try:
        config = load_config()
    except ValueError as e:
        print(f"错误: {e}")
        print("请设置 MIMO_API_KEY 环境变量，或在 .env 文件中配置")
        sys.exit(1)

    # 2. 创建组件
    client = MimoClient(config)
    loop = create_agent_loop(client, model=config.model, workspace_root=os.getcwd())

    # 3. 处理 --resume
    if args.resume:
        _handle_resume(loop, args.resume)

    app = create_agent_app(loop, model=config.model)
    app.run()


def _handle_resume(loop: AgentLoop, resume_arg: str) -> None:
    """处理 --resume 参数

    Args:
        loop: AgentLoop 实例
        resume_arg: "latest" 或 session_id
    """
    if loop._session_store is None:
        print("错误：session store 未启用，无法 resume")
        sys.exit(1)

    if resume_arg == "latest":
        session_data = loop._session_store.load_latest()
    else:
        session_data = loop._session_store.load(resume_arg)

    if session_data is None:
        print(f"错误：找不到 session '{resume_arg}'")
        sys.exit(1)

    # 恢复 session state
    loop.import_session_state(session_data)
    print(f"已恢复 session: {session_data.get('id', 'unknown')}")


if __name__ == "__main__":
    main()
