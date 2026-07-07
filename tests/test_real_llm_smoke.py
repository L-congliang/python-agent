"""真实远程 LLM Smoke 测试

验证真实远程模型链路没有断。

设计决策:
- 为什么用环境门控？
  真实 API 调用需要 key，且可能产生费用。
  默认 pytest tests -q 不应该依赖真实 API。

- 为什么只做 smoke 不做 e2e？
  smoke 只证明"链路没断"，不评估模型能力。
  e2e 需要稳定的 prompt-response 对，不适合真实 API。

- 为什么 prompt 要收敛？
  收敛的 prompt（如"reply with exactly OK"）让断言更稳定。
  模糊的 prompt（如"写一个函数"）会导致断言过脆。

使用方式:
    # 默认跳过
    uv run pytest tests/test_real_llm_smoke.py -q

    # 启用真实 smoke
    RUN_REAL_LLM_SMOKE=1 MIMO_API_KEY=xxx uv run pytest tests/test_real_llm_smoke.py -q
"""

from __future__ import annotations

import os
import tempfile

import pytest


# ============================================================
# 环境门控
# ============================================================


def _is_real_smoke_enabled() -> bool:
    """检查是否启用真实 smoke 测试"""
    return os.environ.get("RUN_REAL_LLM_SMOKE", "0") == "1"


def _get_api_key() -> str | None:
    """获取 API key"""
    return os.environ.get("MIMO_API_KEY")


def _skip_if_not_enabled() -> None:
    """如果未启用则跳过"""
    if not _is_real_smoke_enabled():
        pytest.skip("真实 smoke 未启用（设置 RUN_REAL_LLM_SMOKE=1 启用）")


def _skip_if_no_api_key() -> None:
    """如果没有 API key 则跳过"""
    if not _get_api_key():
        pytest.skip("MIMO_API_KEY 未设置")


# ============================================================
# Client Smoke 测试
# ============================================================


class TestRealClientSmoke:
    """真实 client smoke 测试。"""

    def test_real_client_smoke_skips_without_env(self) -> None:
        """没有设置 RUN_REAL_LLM_SMOKE=1 时跳过"""
        if _is_real_smoke_enabled():
            pytest.skip("已启用，跳过此测试")

        # 这个测试只在未启用时运行
        assert not _is_real_smoke_enabled()

    @pytest.mark.skipif(
        not _is_real_smoke_enabled(),
        reason="真实 smoke 未启用（设置 RUN_REAL_LLM_SMOKE=1 启用）",
    )
    def test_real_client_smoke_runs_with_env(self) -> None:
        """真实 client smoke：验证配置读取、client 初始化、远程 API 可达"""
        _skip_if_no_api_key()

        from agent.core.model import MimoClient, load_config

        # 1. 配置读取没坏
        config = load_config()
        assert config.api_key is not None
        assert config.base_url is not None
        assert config.model is not None

        # 2. client 初始化没坏
        client = MimoClient(config)

        # 3. 远程 API 可达 + 基本响应格式没坏
        try:
            response = client.chat(
                [{"role": "user", "content": "Reply with exactly OK."}],
                max_tokens=10,
            )
        except Exception as e:
            # 网络/API 异常要能区分是远程问题
            pytest.fail(f"远程 API 调用失败（非本地逻辑回归）: {e}")

        # 4. 断言有响应
        assert response is not None
        assert len(response) > 0
        # 收敛 prompt 期望包含 OK
        assert "OK" in response.upper()


# ============================================================
# Agent Loop Smoke 测试
# ============================================================


class TestRealAgentLoopSmoke:
    """真实 agent loop smoke 测试。"""

    def test_real_agent_loop_smoke_skips_without_env(self) -> None:
        """没有设置 RUN_REAL_LLM_SMOKE=1 时跳过"""
        if _is_real_smoke_enabled():
            pytest.skip("已启用，跳过此测试")

        # 这个测试只在未启用时运行
        assert not _is_real_smoke_enabled()

    @pytest.mark.skipif(
        not _is_real_smoke_enabled(),
        reason="真实 smoke 未启用（设置 RUN_REAL_LLM_SMOKE=1 启用）",
    )
    def test_real_agent_loop_smoke_runs_with_env(self) -> None:
        """最小真实 agent loop smoke：验证默认装配路径、tool use -> observation -> final answer"""
        _skip_if_no_api_key()

        from agent.core.model import MimoClient, load_config
        from agent.main import create_agent_loop

        # 1. 创建临时 workspace
        with tempfile.TemporaryDirectory() as tmpdir:
            # 放一个极小文件
            hello_file = os.path.join(tmpdir, "hello.txt")
            with open(hello_file, "w", encoding="utf-8") as f:
                f.write("hello world")

            # 2. 创建 agent loop
            config = load_config()
            client = MimoClient(config)
            loop = create_agent_loop(
                client,
                model=config.model,
                workspace_root=tmpdir,
            )

            # 3. 执行极小任务
            try:
                response = loop.run(
                    "Read the file hello.txt and tell me its content. "
                    "Reply with just the content, nothing else."
                )
            except Exception as e:
                pytest.fail(f"远程 agent loop 调用失败（非本地逻辑回归）: {e}")

            # 4. 断言最终回答包含 hello
            assert response is not None
            assert "hello" in response.lower()

            # 5. 断言至少发生过一次 tool 调用
            # loop._tool_history 记录了工具调用历史
            assert len(loop._tool_history) > 0


# ============================================================
# 边界测试
# ============================================================


class TestRealSmokeEdgeCases:
    """边界情况测试。"""

    def test_skip_logic_works(self) -> None:
        """验证 skip 逻辑正确"""
        # 这个测试总是运行，验证 skip 函数不抛异常
        _is_real_smoke_enabled()
        _get_api_key()

    @pytest.mark.skipif(
        not _is_real_smoke_enabled(),
        reason="真实 smoke 未启用",
    )
    def test_api_key_missing_skip(self) -> None:
        """有 RUN_REAL_LLM_SMOKE 但没 MIMO_API_KEY 时清晰跳过"""
        if _get_api_key():
            pytest.skip("有 API key，跳过此测试")

        # 没有 key 时应该跳过
        _skip_if_no_api_key()
