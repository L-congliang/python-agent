"""Agent 类型系统 - 对齐 Claude Code 的 frontmatter 类型系统

设计决策:
- 为什么需要类型系统？
  让主 Agent 声明意图（"我需要一个 explorer"），系统自动配置工具集和行为。
  比主 Agent 手动指定 tools 列表更安全、更易管理。

- 为什么用注册表模式？
  集中管理所有类型定义，容易审计和修改。
  类型查找是 O(1) 的 dict 查找。

- 为什么有 allowed_tools？
  不同类型有不同的工具需求。explore 只需要读取工具，
  code-reviewer 不需要写入工具。按类型过滤防止误用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("agent.orchestration.agent_type")


@dataclass(frozen=True)
class AgentTypeDefinition:
    """Agent 类型定义 - 对齐 Claude Code 的 frontmatter 类型系统

    每个类型定义了该类 Agent 的行为特征：
    - name: 类型名（唯一标识）
    - description: 什么时候用这个类型
    - allowed_tools: 允许的工具名列表（None = 继承父 Agent 全部工具）
    - system_prompt: 该类型的 system prompt（可选，覆盖默认）
    - default_model: 默认模型（可选）
    - default_max_turns: 默认最大轮次（可选）
    """

    name: str
    description: str
    allowed_tools: list[str] | None = None
    system_prompt: str | None = None
    default_model: str | None = None
    default_max_turns: int | None = None


class AgentTypeRegistry:
    """Agent 类型注册表

    管理所有 Agent 类型定义。内置类型在初始化时自动注册。
    支持自定义类型注册。

    使用方式:
        registry = AgentTypeRegistry()
        explore_type = registry.get("explore")
        all_types = registry.get_all()
    """

    def __init__(self) -> None:
        self._types: dict[str, AgentTypeDefinition] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """注册内置类型"""

        # general-purpose: 所有工具，完整能力
        self.register(AgentTypeDefinition(
            name="general-purpose",
            description="Default agent for most tasks. Has access to all tools.",
            default_max_turns=50,
        ))

        # explore: 只读工具，轻量探索
        self.register(AgentTypeDefinition(
            name="explore",
            description="Thorough codebase investigation and multi-file search. Read-only tools only.",
            allowed_tools=["read", "grep", "glob", "bash"],
            default_max_turns=20,
        ))

        # code-reviewer: 只读工具，代码审查
        self.register(AgentTypeDefinition(
            name="code-reviewer",
            description="Reviews code for bugs, style issues, and potential improvements.",
            allowed_tools=["read", "grep", "glob"],
            default_max_turns=15,
        ))

    def register(self, type_def: AgentTypeDefinition) -> None:
        """注册 Agent 类型

        Args:
            type_def: 类型定义

        Raises:
            ValueError: 类型名已存在
        """
        if type_def.name in self._types:
            raise ValueError(
                f"Agent 类型 '{type_def.name}' 已注册，"
                f"请先调用 unregister('{type_def.name}') 再重新注册"
            )
        self._types[type_def.name] = type_def
        logger.debug("Registered agent type: %s", type_def.name)

    def unregister(self, name: str) -> None:
        """注销 Agent 类型

        Args:
            name: 类型名

        Raises:
            KeyError: 类型不存在
        """
        if name not in self._types:
            raise KeyError(f"Agent 类型 '{name}' 未注册")
        del self._types[name]

    def get(self, name: str) -> AgentTypeDefinition:
        """按名称获取类型定义

        如果类型不存在，回退到 general-purpose。

        Args:
            name: 类型名

        Returns:
            AgentTypeDefinition 实例
        """
        type_def = self._types.get(name)
        if type_def is None:
            logger.warning(
                "Agent 类型 '%s' 不存在，回退到 general-purpose",
                name,
            )
            return self._types["general-purpose"]
        return type_def

    def get_all(self) -> list[AgentTypeDefinition]:
        """获取所有已注册的类型定义"""
        return list(self._types.values())

    def has(self, name: str) -> bool:
        """检查类型是否已注册

        Args:
            name: 类型名

        Returns:
            是否存在
        """
        return name in self._types
