"""Cool Code 入口

MimoClient → AgentLoop → AgentApp

使用方式:
    python -m agent.main
"""

import sys
import logging

from agent.core.model import MimoClient, load_config
from agent.core.loop import AgentLoop, LoopConfig
from agent.tools.registry import ToolRegistry
from agent.cli.app import AgentApp, start_cli_session
from agent.core.types import StreamEvent


def setup_logging(debug: bool = False) -> None:
    """配置日志"""
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(name)s: %(message)s",
        stream=sys.stderr,
    )


def main() -> None:
    """主入口"""
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
    registry = ToolRegistry()
    loop = AgentLoop(client, registry)

    # 3. 创建回调
    def handle_message(msg: str):
        for chunk in loop.run_stream(msg):
            yield StreamEvent(type="text", content=chunk)

    # 4. 启动 UI
    app = AgentApp(on_message=handle_message)
    app.run()


if __name__ == "__main__":
    main()
