"""上下文管理器测试。"""

from __future__ import annotations

import pytest

from agent.context.token_counter import TokenCounter, count_tokens, estimate_tokens
from agent.context.budget import ContextBudget, SectionBudget, create_budget
from agent.context.manager import ContextManager, ContextMetadata


# ============================================================
# TokenCounter 测试
# ============================================================


class TestTokenCounter:
    """TokenCounter 测试。"""

    def test_count_empty(self) -> None:
        counter = TokenCounter()
        assert counter.count("") == 0

    def test_count_simple(self) -> None:
        counter = TokenCounter()
        tokens = counter.count("Hello, world!")
        assert tokens > 0
        assert tokens < 10  # 简单文本应该很少 token

    def test_count_list(self) -> None:
        counter = TokenCounter()
        texts = ["Hello", "World", "foo bar"]
        total = counter.count_list(texts)
        assert total > 0

    def test_count_messages_empty(self) -> None:
        counter = TokenCounter()
        assert counter.count_messages([]) == 0

    def test_count_messages_simple(self) -> None:
        counter = TokenCounter()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        tokens = counter.count_messages(messages)
        assert tokens > 0


class TestCountTokens:
    """count_tokens 函数测试。"""

    def test_empty(self) -> None:
        assert count_tokens("") == 0

    def test_simple(self) -> None:
        tokens = count_tokens("Hello, world!")
        assert tokens > 0

    def test_estimate_tokens_empty(self) -> None:
        assert estimate_tokens("") == 0

    def test_estimate_tokens_simple(self) -> None:
        tokens = estimate_tokens("Hello, world!")
        assert tokens > 0


# ============================================================
# ContextBudget 测试
# ============================================================


class TestContextBudget:
    """ContextBudget 测试。"""

    def test_default_budget(self) -> None:
        budget = ContextBudget()
        assert budget.total_budget == 12000
        assert len(budget.sections) == 5

    def test_get_section(self) -> None:
        budget = ContextBudget()
        prefix = budget.get_section("prefix")
        assert prefix is not None
        assert prefix.name == "prefix"
        assert prefix.is_protected is True

    def test_get_section_not_found(self) -> None:
        budget = ContextBudget()
        assert budget.get_section("nonexistent") is None

    def test_get_cuttable_sections(self) -> None:
        budget = ContextBudget()
        cuttable = budget.get_cuttable_sections()
        # prefix 和 current_request 不可裁剪
        names = [s.name for s in cuttable]
        assert "prefix" not in names
        assert "current_request" not in names
        assert "history" in names
        assert "memory" in names
        assert "tools" in names


class TestCreateBudget:
    """create_budget 工厂函数测试。"""

    def test_default(self) -> None:
        budget = create_budget()
        assert budget.total_budget == 12000

    def test_custom(self) -> None:
        budget = create_budget(8000)
        assert budget.total_budget == 8000
        # 各 section 按比例调整
        prefix = budget.get_section("prefix")
        assert prefix is not None
        assert prefix.max_tokens < 3600  # 按比例缩小


# ============================================================
# ContextManager 测试
# ============================================================


class TestContextManager:
    """ContextManager 测试。"""

    def test_build_prompt_no_truncation(self) -> None:
        """未超出预算时，不裁剪"""
        manager = ContextManager()
        prompt, metadata = manager.build_prompt(
            prefix="You are a coding agent.",
            tools="可用工具:\n- bash: 执行命令",
            memory="",
            history="",
            current_request="帮我写一个 hello world",
        )
        assert len(prompt) > 0
        assert metadata.was_truncated is False

    def test_build_prompt_with_truncation(self) -> None:
        """超出预算时，裁剪 history"""
        budget = create_budget(100)  # 很小的预算
        manager = ContextManager(budget)

        # 构造很长的 history
        long_history = "user: hello\n" * 100
        prompt, metadata = manager.build_prompt(
            prefix="You are a coding agent.",
            tools="可用工具:\n- bash: 执行命令",
            memory="",
            history=long_history,
            current_request="帮我写一个 hello world",
        )
        assert len(prompt) > 0
        assert metadata.was_truncated is True
        # history 应该被裁剪
        assert metadata.sections["history"].was_truncated is True

    def test_build_prompt_prefix_protected(self) -> None:
        """prefix 不被裁剪"""
        budget = create_budget(500)
        manager = ContextManager(budget)

        long_history = "user: hello\n" * 100
        prompt, metadata = manager.build_prompt(
            prefix="You are a coding agent.",
            tools="可用工具:\n- bash: 执行命令",
            memory="",
            history=long_history,
            current_request="帮我写一个 hello world",
        )
        # prefix 不应该被裁剪
        assert metadata.sections["prefix"].was_truncated is False

    def test_build_prompt_current_request_protected(self) -> None:
        """current_request 不被裁剪"""
        budget = create_budget(500)
        manager = ContextManager(budget)

        long_history = "user: hello\n" * 100
        prompt, metadata = manager.build_prompt(
            prefix="You are a coding agent.",
            tools="可用工具:\n- bash: 执行命令",
            memory="",
            history=long_history,
            current_request="帮我写一个 hello world",
        )
        # current_request 不应该被裁剪
        assert metadata.sections["current_request"].was_truncated is False

    def test_metadata_sections(self) -> None:
        """元数据包含所有 section"""
        manager = ContextManager()
        prompt, metadata = manager.build_prompt(
            prefix="You are a coding agent.",
            tools="可用工具:\n- bash: 执行命令",
            memory="用户偏好: 简洁风格",
            history="user: hello\nassistant: hi",
            current_request="帮我写一个 hello world",
        )
        assert "prefix" in metadata.sections
        assert "tools" in metadata.sections
        assert "memory" in metadata.sections
        assert "history" in metadata.sections
        assert "current_request" in metadata.sections

    def test_metadata_budget(self) -> None:
        """元数据记录每个 section 的预算"""
        manager = ContextManager()
        prompt, metadata = manager.build_prompt(
            prefix="You are a coding agent.",
            tools="",
            memory="",
            history="",
            current_request="test",
        )
        prefix_meta = metadata.sections["prefix"]
        assert prefix_meta.budget > 0

    def test_empty_inputs(self) -> None:
        """空输入也能正常工作"""
        manager = ContextManager()
        prompt, metadata = manager.build_prompt()
        assert prompt == ""
        assert metadata.was_truncated is False

    def test_custom_budget(self) -> None:
        """自定义预算配置"""
        budget = ContextBudget(total_budget=5000)
        manager = ContextManager(budget)
        prompt, metadata = manager.build_prompt(
            prefix="test",
            current_request="test",
        )
        assert len(prompt) > 0
