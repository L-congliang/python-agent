"""
工具注册表 - 管理工具的注册和发现

对齐 Claude Code 的 tools.ts 中的 getAllBaseTools() 和相关函数。

设计决策:
- 为什么不直接用 dict？
  因为需要类型检查、格式转换、统一执行流程。
- validate_and_execute 的错误处理？
  每一步失败都返回 ToolResult(is_error=True)，不抛异常。
  这样主循环可以统一处理，不需要 try/except。
- filter_by_names 和 clone？
  子 Agent 需要受限的工具集。filter_by_names 创建只包含指定工具的新注册表。
  clone 创建深拷贝，避免修改影响原注册表。
"""

from __future__ import annotations

from agent.tools.base import Tool
from agent.core.types import ToolResult, PermissionBehavior
from agent.core.context import ToolUseContext


def register_base_tools(registry: "ToolRegistry") -> "ToolRegistry":
    """向注册表中注入默认基础工具。"""
    from agent.tools.bash import bash_tool
    from agent.tools.file_edit import file_edit_tool
    from agent.tools.file_read import file_read_tool
    from agent.tools.file_write import file_write_tool
    from agent.tools.glob import glob_tool
    from agent.tools.grep import grep_tool

    for tool in (
        bash_tool,
        file_read_tool,
        file_write_tool,
        file_edit_tool,
        grep_tool,
        glob_tool,
    ):
        if registry.get(tool.name) is None:
            registry.register(tool)
    return registry


class ToolRegistry:
    """工具注册表

    职责:
    - 管理工具的注册和注销
    - 提供工具查询（按名称、获取全部）
    - 将工具转换为 Anthropic API 的 tool 格式
    - 执行前校验 + 权限检查 + 执行

    使用方式:
        registry = ToolRegistry()
        registry.register(bash_tool)
        registry.register(file_read_tool)

        # 模型返回 tool_use 时
        result = registry.validate_and_execute(
            name="bash",
            arguments={"command": "ls"},
            context=tool_use_context,
        )
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具

        Args:
            tool: 实现了 Tool 协议的对象

        Raises:
            TypeError: tool 没有实现 Tool 协议
            ValueError: 工具名称已存在
        """
        # 运行时类型检查
        if not isinstance(tool, Tool):
            raise TypeError(
                f"工具必须实现 Tool 协议，收到: {type(tool).__name__}"
            )

        # 重复检查
        if tool.name in self._tools:
            raise ValueError(
                f"工具 '{tool.name}' 已注册，"
                f"请先调用 unregister('{tool.name}') 再重新注册"
            )

        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """注销工具

        Args:
            name: 工具名称

        Raises:
            KeyError: 工具不存在
        """
        if name not in self._tools:
            raise KeyError(f"工具 '{name}' 未注册")
        del self._tools[name]

    def get(self, name: str) -> Tool | None:
        """按名称获取工具

        Args:
            name: 工具名称

        Returns:
            Tool 实例，或 None
        """
        return self._tools.get(name)

    def get_all(self) -> list[Tool]:
        """获取所有已注册的工具"""
        return list(self._tools.values())

    def get_enabled_tools(self) -> list[Tool]:
        """获取所有启用的工具

        过滤掉 is_enabled() 返回 False 的工具。
        """
        return [t for t in self._tools.values() if t.is_enabled()]

    def to_anthropic_tools(self) -> list[dict]:
        """转换为 Anthropic API 的 tools 格式

        返回格式:
        [
            {
                "name": "bash",
                "description": "Execute a shell command",
                "input_schema": {
                    "type": "object",
                    "properties": {...},
                    "required": [...]
                }
            },
            ...
        ]
        """
        result = []
        for tool in self.get_enabled_tools():
            result.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            })
        return result

    def validate_and_execute(
        self,
        name: str,
        arguments: dict,
        context: ToolUseContext,
    ) -> ToolResult:
        """校验权限 + 校验输入 + 执行工具

        完整的执行流程:
        1. 查找工具
        2. 检查 is_enabled
        3. validate_input（输入校验）
        4. check_permissions（权限检查）
        5. execute（执行）
        6. 返回结果

        任何步骤失败都返回 ToolResult(is_error=True)。

        Args:
            name: 工具名称
            arguments: 参数字典
            context: 工具执行上下文

        Returns:
            ToolResult 执行结果
        """

        # 1. 查找工具
        tool = self.get(name)
        if tool is None:
            return ToolResult(
                output=f"工具 '{name}' 不存在。可用工具: {', '.join(self._tools.keys())}",
                is_error=True,
            )

        # 2. 检查 is_enabled
        if not tool.is_enabled():
            return ToolResult(
                output=f"工具 '{name}' 已禁用",
                is_error=True,
            )

        # 3. validate_input（输入校验）
        validation = tool.validate_input(arguments, context)
        if not validation.is_valid:
            return ToolResult(
                output=f"输入校验失败: {validation.message}",
                is_error=True,
            )

        # 4. check_permissions（权限检查）
        permission = tool.check_permissions(arguments, context)
        if permission.behavior == PermissionBehavior.DENY:
            return ToolResult(
                output=f"权限被拒绝: {permission.message}",
                is_error=True,
            )
        if permission.behavior == PermissionBehavior.ASK:
            # ASK 的处理交给主循环（F04），这里先返回错误
            # TODO: F04 实现后，ASK 应该触发用户交互
            return ToolResult(
                output=f"需要用户确认: {permission.message}",
                is_error=True,
            )

        # 如果权限检查修改了 input，使用修改后的版本
        final_input = permission.updated_input if permission.updated_input is not None else arguments

        # 5. execute（执行）
        try:
            return tool.execute(final_input, context)
        except Exception as e:
            # 工具不应该抛异常，但我们要防御性地处理
            return ToolResult(
                output=f"工具 '{name}' 执行时抛出异常: {type(e).__name__}: {e}",
                is_error=True,
            )

    def filter_by_names(self, names: list[str]) -> ToolRegistry:
        """按名称过滤工具，创建新的注册表

        用于子 Agent 的工具集限制。
        只包含指定名称的工具，忽略不存在的名称。

        Args:
            names: 允许的工具名列表

        Returns:
            新的 ToolRegistry 实例，只包含指定的工具
        """
        filtered = ToolRegistry()
        for name in names:
            tool = self._tools.get(name)
            if tool is not None:
                filtered._tools[name] = tool
        return filtered

    def clone(self) -> ToolRegistry:
        """创建注册表的浅拷贝

        子 Agent 需要独立的注册表，但工具实例可以共享（工具是无状态的）。

        Returns:
            新的 ToolRegistry 实例，包含相同的工具引用
        """
        cloned = ToolRegistry()
        cloned._tools = dict(self._tools)
        return cloned
