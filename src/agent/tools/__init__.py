"""
工具系统 - 对齐 Claude Code 的 Tool 系统

包含:
- base: Tool Protocol + build_tool 工厂函数
- registry: ToolRegistry 工具注册表
- bash: bash_tool 实例
- file_read: file_read_tool 实例
- file_write: file_write_tool 实例
- file_edit: file_edit_tool 实例
- grep: grep_tool 实例
"""

from agent.tools.base import Tool, ToolImpl, build_tool
from agent.tools.registry import ToolRegistry
from agent.tools.bash import bash_tool
from agent.tools.file_read import file_read_tool
from agent.tools.file_write import file_write_tool
from agent.tools.file_edit import file_edit_tool
from agent.tools.grep import grep_tool

__all__ = [
    "Tool",
    "ToolImpl",
    "build_tool",
    "ToolRegistry",
    "bash_tool",
    "file_read_tool",
    "file_write_tool",
    "file_edit_tool",
    "grep_tool",
]
