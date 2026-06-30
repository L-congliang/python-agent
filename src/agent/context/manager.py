"""上下文管理器 - 预算制 prompt 组装

替代现有的"超了才压缩"模式，改为"每次组装时按预算裁剪"。

设计决策:
- 为什么用预算制而不是 LLM 摘要？
  预算制是主动控制，不需要额外 API 调用。
  LLM 摘要是被动补救，增加延迟和成本，且摘要质量不可控。

- 为什么保留最近 30% 的 history？
  太少会丢失近期上下文，太多则压缩效果差。
  30% 是经验值，Claude Code 也用类似比例。

- 为什么 prefix 和 current_request 不裁剪？
  prefix 是 agent 的身份和规则，不能丢。
  current_request 是用户当前的需求，不能丢。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent.context.token_counter import TokenCounter
from agent.context.budget import ContextBudget, SectionBudget, DEFAULT_BUDGET

logger = logging.getLogger("agent.context.manager")


@dataclass
class SectionMetadata:
    """单个 section 的元数据

    Attributes:
        name: section 名称
        raw_chars: 原始字符数
        rendered_chars: 渲染后字符数
        raw_tokens: 原始 token 数
        rendered_tokens: 渲染后 token 数
        was_truncated: 是否被裁剪
        budget: 分配的 token 预算
    """
    name: str
    raw_chars: int = 0
    rendered_chars: int = 0
    raw_tokens: int = 0
    rendered_tokens: int = 0
    was_truncated: bool = False
    budget: int = 0


@dataclass
class ContextMetadata:
    """prompt 组装的元数据

    Attributes:
        total_raw_tokens: 原始总 token 数
        total_rendered_tokens: 渲染后总 token 数
        was_truncated: 是否触发裁剪
        sections: 各 section 的元数据
    """
    total_raw_tokens: int = 0
    total_rendered_tokens: int = 0
    was_truncated: bool = False
    sections: dict[str, SectionMetadata] = field(default_factory=dict)


class ContextManager:
    """上下文管理器

    职责:
    - 按 section 分配 token 预算
    - 超预算时按优先级裁剪
    - 记录元数据

    使用方式:
        manager = ContextManager()
        prompt, metadata = manager.build_prompt(
            prefix="You are a coding agent...",
            tools="可用工具:\n- bash: 执行命令...",
            memory="用户偏好: 简洁风格",
            history=messages,
            current_request="帮我写一个 hello world",
        )
    """

    def __init__(self, budget: ContextBudget | None = None) -> None:
        """初始化上下文管理器

        Args:
            budget: 预算配置，None 使用默认配置
        """
        self._budget = budget or DEFAULT_BUDGET
        self._counter = TokenCounter()

    def build_prompt(
        self,
        prefix: str = "",
        tools: str = "",
        memory: str = "",
        history: str = "",
        current_request: str = "",
    ) -> tuple[str, ContextMetadata]:
        """组装 prompt

        Args:
            prefix: 系统提示词
            tools: 工具描述
            memory: 工作记忆
            history: 历史消息（已格式化为文本）
            current_request: 当前请求

        Returns:
            (prompt, metadata) 元组
        """
        # 1. 计算各 section 的原始 token 数
        sections_raw = {
            "prefix": prefix,
            "tools": tools,
            "memory": memory,
            "history": history,
            "current_request": current_request,
        }

        sections_tokens: dict[str, int] = {}
        for name, text in sections_raw.items():
            sections_tokens[name] = self._counter.count(text)

        total_raw = sum(sections_tokens.values())

        # 2. 检查是否需要裁剪
        metadata = ContextMetadata(
            total_raw_tokens=total_raw,
            total_rendered_tokens=total_raw,
            was_truncated=False,
        )

        # 初始化各 section 元数据
        for name, text in sections_raw.items():
            section_budget = self._budget.get_section(name)
            metadata.sections[name] = SectionMetadata(
                name=name,
                raw_chars=len(text),
                rendered_chars=len(text),
                raw_tokens=sections_tokens[name],
                rendered_tokens=sections_tokens[name],
                was_truncated=False,
                budget=section_budget.max_tokens if section_budget else 0,
            )

        # 3. 如果超出预算，按优先级裁剪
        if total_raw > self._budget.total_budget:
            metadata.was_truncated = True
            sections_tokens = self._trim_sections(sections_tokens, metadata)

        # 4. 组装 prompt
        parts = []
        for name in ["prefix", "tools", "memory", "history", "current_request"]:
            text = sections_raw[name]
            if text:
                # 按 token 裁剪文本
                trimmed_text = self._trim_text_to_tokens(
                    text, sections_tokens[name]
                )
                parts.append(trimmed_text)

        prompt = "\n\n".join(parts)
        metadata.total_rendered_tokens = sum(sections_tokens.values())

        return prompt, metadata

    def _trim_sections(
        self,
        sections_tokens: dict[str, int],
        metadata: ContextMetadata,
    ) -> dict[str, int]:
        """按优先级裁剪各 section

        裁剪顺序（从低到高）：history → tool_results → memory → tools → prefix

        Args:
            sections_tokens: 各 section 的 token 数
            metadata: 元数据（会被修改）

        Returns:
            裁剪后的各 section token 数
        """
        result = dict(sections_tokens)
        total = sum(result.values())
        overage = total - self._budget.total_budget

        if overage <= 0:
            return result

        # 获取可裁剪的 section（按优先级从低到高）
        cuttable = self._budget.get_cuttable_sections()

        for section_config in cuttable:
            if overage <= 0:
                break

            name = section_config.name
            current_tokens = result.get(name, 0)
            floor = section_config.floor_tokens

            # 可以裁剪的数量
            can_cut = current_tokens - floor
            if can_cut <= 0:
                continue

            # 实际裁剪的数量
            will_cut = min(can_cut, overage)
            result[name] = current_tokens - will_cut
            overage -= will_cut

            # 更新元数据
            if name in metadata.sections:
                metadata.sections[name].was_truncated = True
                metadata.sections[name].rendered_tokens = result[name]

            logger.info(
                "Trimmed section '%s': %d -> %d tokens (cut %d)",
                name, current_tokens, result[name], will_cut,
            )

        return result

    def _trim_text_to_tokens(self, text: str, target_tokens: int) -> str:
        """将文本裁剪到目标 token 数

        Args:
            text: 原始文本
            target_tokens: 目标 token 数

        Returns:
            裁剪后的文本
        """
        if not text:
            return text

        current_tokens = self._counter.count(text)
        if current_tokens <= target_tokens:
            return text

        # 二分查找合适的长度
        low, high = 0, len(text)
        while low < high:
            mid = (low + high) // 2
            if self._counter.count(text[:mid]) <= target_tokens:
                low = mid + 1
            else:
                high = mid

        # 回退到最后一个满足条件的位置
        trimmed = text[:low]
        while self._counter.count(trimmed) > target_tokens and len(trimmed) > 0:
            trimmed = trimmed[:-1]

        return trimmed
