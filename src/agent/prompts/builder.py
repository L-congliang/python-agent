"""SystemPromptBuilder - 结构化 system prompt 组装

将 system prompt 分为 4 个模块：
1. Identity — agent 身份定义
2. Behavioral Guidelines — 行为准则（通用原则 + 具体规则）
3. Tool Selection Guide — 工具选择指南
4. Dynamic Context — 动态上下文（记忆、工具列表、SubAgent）

设计决策:
- 为什么用 builder 模式而不是字符串拼接？
  因为每个模块有独立逻辑，builder 让每个模块可测试、可复用。
  之前 _build_system_prompt() 把所有逻辑塞在 loop.py 里，职责不清。

- 为什么每个模块是 static method？
  因为模块本身不依赖实例状态，只依赖输入参数。
  static method 方便单独测试每个模块。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.tools.registry import ToolRegistry
    from agent.memory.manager import MemoryManager


class SystemPromptBuilder:
    """System Prompt 构建器

    使用方式:
        prompt = SystemPromptBuilder.build(
            memory=memory,
            registry=registry,
            subagent_registered=True,
            plan_mode=False,
        )
    """

    @staticmethod
    def build_identity() -> str:
        """构建 Identity 部分

        Returns:
            Identity 文本
        """
        return (
            "你是 Cool Code，一个运行在终端里的 AI 编程助手。\n\n"
            "你的能力：\n"
            "- 读写和编辑代码文件\n"
            "- 搜索代码库（内容搜索和文件发现）\n"
            "- 执行 shell 命令（测试、构建、Git）\n"
            "- 派生子 Agent 并行处理复杂任务\n\n"
            "你的工作方式：\n"
            "- 通过工具与文件系统交互\n"
            "- 每次回复可以调用多个工具\n"
            "- 工具结果会返回给你，你基于结果继续推理"
        )

    @staticmethod
    def build_behavior_guidelines() -> str:
        """构建 Behavioral Guidelines 部分

        通用原则收窄高层行为空间，具体规则约束高频操作。
        两者互补：通用原则覆盖广，具体规则精度高。

        Returns:
            Behavioral Guidelines 文本
        """
        return (
            "## 行为准则\n\n"
            "通用原则：\n"
            "- 先理解再动手：读文件 → 理解 → 改文件\n"
            "- 最小改动：只改必要的部分，不重构无关代码\n"
            "- 出错时分析原因：看错误信息，理解为什么失败，不要盲目重试\n\n"
            "具体规则：\n"
            "- 改文件前必须先用 file_read 读取内容\n"
            "- 优先用 file_edit 而不是 file_write（edit 是精确替换，write 会覆盖整个文件）\n"
            "- 优先用 grep 而不是 bash grep（grep 工具更方便，结果格式更好）\n"
            "- 工具报错不要重复相同调用，先分析错误原因"
        )

    @staticmethod
    def build_tool_selection_guide() -> str:
        """构建 Tool Selection Guide 部分

        集中描述工具选择策略，让模型知道什么时候用什么工具。
        约 200 token。

        Returns:
            Tool Selection Guide 文本
        """
        return (
            "## 工具选择指南\n\n"
            "要做什么 → 用什么工具：\n"
            "- 读文件/看代码 → file_read（支持行范围，大文件不会一次全读）\n"
            "- 改已有文件的某几行 → file_edit（精确替换，不需要重写整个文件）\n"
            "- 创建新文件 → file_write（会覆盖已有文件，慎用）\n"
            "- 搜索代码内容 → grep（用正则，比 bash grep 更方便）\n"
            "- 找文件路径 → glob（用模式匹配如 **/*.py）\n"
            "- 运行命令/测试 → bash\n"
            "- 复杂多步任务 → subagent（派生子 Agent 并行执行）\n\n"
            "重要：\n"
            "- 改文件前必须先用 file_read 读取内容\n"
            "- file_edit 比 file_write 更安全，优先用 file_edit\n"
            "- grep 比 bash grep 更好，不要用 bash grep"
        )

    @classmethod
    def build_prefix(cls, plan_mode: bool = False) -> str:
        """构建静态前缀（Identity + Behavior + Tool Guide）

        不包含 dynamic context（memory、tools 列表、subagent 指南）。
        供 ContextManager 使用，作为 prompt 组装的 prefix section。

        Args:
            plan_mode: 是否处于 Plan Mode

        Returns:
            静态前缀文本
        """
        parts: list[str] = []
        if plan_mode:
            parts.append(cls.build_plan_mode_marker())
        parts.append(cls.build_identity())
        parts.append(cls.build_behavior_guidelines())
        parts.append(cls.build_tool_selection_guide())
        return "\n\n".join(parts)

    @staticmethod
    def build_plan_mode_marker() -> str:
        """构建 Plan Mode 标记

        Returns:
            Plan Mode 标记文本
        """
        return (
            "## 当前模式：计划模式\n\n"
            "你正处于计划模式。不要执行任何修改操作。\n"
            "请先分析需求，输出结构化计划，包含：\n"
            "- 目标：要完成什么\n"
            "- 步骤列表：分几步完成\n"
            "- 每步使用的工具\n"
            "- 预期结果\n\n"
            "等待用户确认后再执行。"
        )

    @staticmethod
    def build_dynamic_context(
        memory: MemoryManager | None = None,
        registry: ToolRegistry | None = None,
        subagent_registered: bool = False,
    ) -> str:
        """构建 Dynamic Context 部分

        包含记忆信息、工具列表、SubAgent 使用指南。

        Args:
            memory: 记忆管理器
            registry: 工具注册表
            subagent_registered: SubAgent 是否已注册

        Returns:
            Dynamic Context 文本
        """
        parts: list[str] = []

        # 记忆信息
        if memory:
            memory_output = memory.render()
            if memory_output:
                parts.append(memory_output)

        # 工具列表
        if registry:
            tools = registry.get_enabled_tools()
            if tools:
                tool_desc = "可用工具:\n"
                for tool in tools:
                    tool_desc += f"- {tool.name}: {tool.description}\n"
                parts.append(tool_desc)

        # SubAgent 使用指南
        if subagent_registered:
            parts.append(
                "## SubAgent 使用指南\n"
                "当任务可以并行执行、需要独立上下文、或涉及大量文件搜索时，"
                "使用 subagent 工具派生子 Agent。\n"
                "适用场景：\n"
                "- 搜索大量文件（如搜索所有 TODO）\n"
                "- 复杂多步任务（可以拆分为独立子任务）\n"
                "- 需要独立上下文的任务（避免污染主对话）\n"
                "不适用场景：\n"
                "- 简单单步操作（直接用现有工具更快）\n"
                "- 需要用户交互的任务（子 Agent 不能向用户提问）"
            )

        return "\n\n".join(parts)

    @classmethod
    def build(
        cls,
        memory: MemoryManager | None = None,
        registry: ToolRegistry | None = None,
        subagent_registered: bool = False,
        plan_mode: bool = False,
        extra_prompt: str = "",
    ) -> str:
        """组装完整的 system prompt

        按 Identity → Behavior → Tool Guide → Dynamic Context 顺序拼接。
        plan_mode 为 True 时，在最前面插入 Plan Mode 标记。

        Args:
            memory: 记忆管理器
            registry: 工具注册表
            subagent_registered: SubAgent 是否已注册
            plan_mode: 是否处于 Plan Mode
            extra_prompt: 额外的 prompt 内容（追加到末尾）

        Returns:
            完整的 system prompt
        """
        parts: list[str] = []

        # Plan Mode 标记（如果启用）
        if plan_mode:
            parts.append(cls.build_plan_mode_marker())

        # Identity
        parts.append(cls.build_identity())

        # Behavioral Guidelines
        parts.append(cls.build_behavior_guidelines())

        # Tool Selection Guide
        parts.append(cls.build_tool_selection_guide())

        # Dynamic Context
        dynamic = cls.build_dynamic_context(
            memory=memory,
            registry=registry,
            subagent_registered=subagent_registered,
        )
        if dynamic:
            parts.append(dynamic)

        # 额外 prompt
        if extra_prompt:
            parts.append(extra_prompt)

        return "\n\n".join(parts)
