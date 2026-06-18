"""
工具系统 - 对齐 Claude Code 的 Tool 系统

包含:
- base: Tool Protocol + build_tool 工厂函数
- registry: ToolRegistry 工具注册表
"""

from agent.tools.base import Tool, ToolImpl, build_tool
from agent.tools.registry import ToolRegistry

__all__ = [
    "Tool",
    "ToolImpl",
    "build_tool",
    "ToolRegistry",
]
