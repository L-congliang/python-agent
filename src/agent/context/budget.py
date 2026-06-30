"""上下文预算配置 - 定义 prompt 各 section 的 token 预算

设计决策:
- 为什么分 5 个 section？
  对齐 Claude Code 的 prompt 结构：
  - prefix: 系统提示词（不裁剪）
  - tools: 工具描述
  - memory: 工作记忆
  - history: 历史消息
  - current_request: 当前请求（不裁剪）

- 为什么有 floor（最低保证）？
  防止某个 section 被完全裁掉。
  比如 history 被裁到 0，agent 就完全忘记之前发生了什么。

- 为什么 prefix 和 current_request 不裁剪？
  prefix 是 agent 的身份和规则，不能丢。
  current_request 是用户当前的需求，不能丢。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SectionBudget:
    """单个 section 的预算配置

    Attributes:
        name: section 名称
        max_tokens: 最大 token 数
        floor_tokens: 最低保证 token 数（裁剪下限）
        is_protected: 是否受保护（不裁剪）
    """
    name: str
    max_tokens: int
    floor_tokens: int = 0
    is_protected: bool = False


@dataclass
class ContextBudget:
    """上下文预算配置

    默认配置（总预算 12000 token）：
    - prefix: 3600（不裁剪）
    - tools: 2000（floor 500）
    - memory: 1600（floor 400）
    - history: 5200（floor 1500）
    - current_request: 不限（不裁剪）

    使用方式:
        budget = ContextBudget()
        budget = ContextBudget(total_budget=8000)  # 自定义总预算
    """
    total_budget: int = 12000

    # 各 section 预算配置
    sections: list[SectionBudget] = field(default_factory=list)

    def __post_init__(self) -> None:
        """如果未提供 sections，使用默认配置"""
        if not self.sections:
            self.sections = self._default_sections()

    def _default_sections(self) -> list[SectionBudget]:
        """默认 section 配置"""
        return [
            SectionBudget(
                name="prefix",
                max_tokens=3600,
                floor_tokens=3600,
                is_protected=True,
            ),
            SectionBudget(
                name="tools",
                max_tokens=2000,
                floor_tokens=500,
            ),
            SectionBudget(
                name="memory",
                max_tokens=1600,
                floor_tokens=400,
            ),
            SectionBudget(
                name="history",
                max_tokens=5200,
                floor_tokens=1500,
            ),
            SectionBudget(
                name="current_request",
                max_tokens=999999,  # 不限
                floor_tokens=999999,
                is_protected=True,
            ),
        ]

    def get_section(self, name: str) -> SectionBudget | None:
        """按名称获取 section 配置"""
        for section in self.sections:
            if section.name == name:
                return section
        return None

    def get_cuttable_sections(self) -> list[SectionBudget]:
        """获取可裁剪的 section（按优先级从低到高排序）

        裁剪顺序：history → tool_results → memory → tools → prefix
        """
        cuttable = [s for s in self.sections if not s.is_protected]
        # 按 max_tokens 从大到小排序（大的先裁）
        cuttable.sort(key=lambda s: s.max_tokens, reverse=True)
        return cuttable


# 默认预算配置
DEFAULT_BUDGET = ContextBudget()


def create_budget(total_budget: int = 12000) -> ContextBudget:
    """创建预算配置的工厂函数

    Args:
        total_budget: 总预算 token 数

    Returns:
        ContextBudget 实例
    """
    # 按比例调整各 section
    ratio = total_budget / 12000
    sections = [
        SectionBudget(
            name="prefix",
            max_tokens=int(3600 * ratio),
            floor_tokens=int(3600 * ratio),
            is_protected=True,
        ),
        SectionBudget(
            name="tools",
            max_tokens=int(2000 * ratio),
            floor_tokens=int(500 * ratio),
        ),
        SectionBudget(
            name="memory",
            max_tokens=int(1600 * ratio),
            floor_tokens=int(400 * ratio),
        ),
        SectionBudget(
            name="history",
            max_tokens=int(5200 * ratio),
            floor_tokens=int(1500 * ratio),
        ),
        SectionBudget(
            name="current_request",
            max_tokens=999999,
            floor_tokens=999999,
            is_protected=True,
        ),
    ]
    return ContextBudget(total_budget=total_budget, sections=sections)
