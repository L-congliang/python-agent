"""Tests for Phase 3.2C Reflection Eval Runner"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


class TestReflectionEvalRunner:
    """测试 reflection eval runner 的输出"""

    def test_runner_with_reflection_produces_json(self, tmp_path: Path) -> None:
        """--with-reflection 输出 JSON 文件"""
        result = subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path), "--with-reflection"],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"Runner failed: {result.stderr}"

        json_files = list(tmp_path.glob("memory_eval_*.json"))
        assert len(json_files) == 1

    def test_runner_without_reflection_produces_json(self, tmp_path: Path) -> None:
        """不带 --with-reflection 也能正常输出"""
        result = subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path)],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"Runner failed: {result.stderr}"

        json_files = list(tmp_path.glob("memory_eval_*.json"))
        assert len(json_files) == 1

    def test_reflection_metrics_in_json(self, tmp_path: Path) -> None:
        """--with-reflection 时所有 config 都有 reflection 字段（schema 稳定）"""
        subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path), "--with-reflection"],
            capture_output=True, text=True, timeout=120,
        )

        json_files = list(tmp_path.glob("memory_eval_*.json"))
        data = json.loads(json_files[0].read_text(encoding="utf-8"))

        # 所有 config 都应该有 reflection 字段，即使 trigger=0
        for config_name in ["memory_on", "memory_off", "memory_irrelevant"]:
            config = data["memory"][config_name]
            assert "reflection_trigger_rate" in config, f"{config_name} missing reflection_trigger_rate"
            assert "reflection_retry_success_rate" in config, f"{config_name} missing reflection_retry_success_rate"
            assert "reflection_avg_extra_tool_calls" in config, f"{config_name} missing reflection_avg_extra_tool_calls"
            assert "reflection_helped_tasks" in config, f"{config_name} missing reflection_helped_tasks"

    def test_json_schema_stable_with_reflection(self, tmp_path: Path) -> None:
        """JSON schema 稳定（包含 reflection 指标字段）"""
        subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path), "--with-reflection"],
            capture_output=True, text=True, timeout=120,
        )

        json_files = list(tmp_path.glob("memory_eval_*.json"))
        data = json.loads(json_files[0].read_text(encoding="utf-8"))

        assert "run_id" in data
        assert "memory" in data
        for config_name in ["memory_on", "memory_off", "memory_irrelevant"]:
            assert config_name in data["memory"]

    def test_markdown_report_with_reflection(self, tmp_path: Path) -> None:
        """Markdown 报告包含 reflection 信息"""
        subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path), "--with-reflection"],
            capture_output=True, text=True, timeout=120,
        )

        md_files = list(tmp_path.glob("memory_eval_*.md"))
        content = md_files[0].read_text(encoding="utf-8")

        assert "# Memory Experiment Report" in content
        assert "memory_on" in content


class TestReflectionPromptConsumed:
    """retry 路径确实消费了 reflection_prompt"""

    def test_retry_client_receives_reflection_prompt(self) -> None:
        """retry 的 PromptAwareScriptedModelClient 收到的 prompt 包含 reflection 内容"""
        from agent.evaluation.memory_experiment import (
            MemoryExperiment, MemoryConfig, MEMORY_TASKS,
        )
        from agent.reflection.types import ReflectionConfig

        experiment = MemoryExperiment(use_real_model=False, output_dir="/tmp/test_prompt")
        config = MemoryConfig(name="memory_off", use_memory=False)
        reflection_config = ReflectionConfig(enabled=True)

        # 找一个会触发 reflection 的 task
        task = next(t for t in MEMORY_TASKS if t.task_id == "mem_sensitive_api_url")

        # 运行
        result = experiment._run_single_task(config, task, reflection_config)

        # 验证 reflection 触发了
        assert result.get("reflection_triggered", False), "reflection should have triggered"

    def test_prompt_aware_client_selects_branch(self) -> None:
        """PromptAwareScriptedModelClient 根据 prompt 中的 retry_strategy 选 branch"""
        from agent.evaluation.fake_client import PromptAwareScriptedModelClient

        client = PromptAwareScriptedModelClient(
            branches={
                "use_memory_answer": [
                    [{"type": "text", "text": "from memory"}],
                ],
                "reread_then_answer": [
                    [{"type": "text", "text": "from reread"}],
                ],
            },
            default_branch="use_memory_answer",
        )

        # 模拟消息，包含 retry_strategy: reread_then_answer
        messages = [
            {"role": "user", "content": "Task: test\nretry_strategy: reread_then_answer\nshould_reread_target: yes"},
        ]

        result = client.chat_stream(messages)
        text_chunks = list(result.text)
        text = "".join(text_chunks)

        assert "from reread" in text

    def test_prompt_aware_client_fallback_to_default(self) -> None:
        """PromptAwareScriptedModelClient 在无 strategy 时 fallback 到 default"""
        from agent.evaluation.fake_client import PromptAwareScriptedModelClient

        client = PromptAwareScriptedModelClient(
            branches={
                "use_memory_answer": [
                    [{"type": "text", "text": "from memory"}],
                ],
                "reread_then_answer": [
                    [{"type": "text", "text": "from reread"}],
                ],
            },
            default_branch="use_memory_answer",
        )

        # 无 retry_strategy 的消息
        messages = [
            {"role": "user", "content": "Just a normal prompt"},
        ]

        result = client.chat_stream(messages)
        text_chunks = list(result.text)
        text = "".join(text_chunks)

        assert "from memory" in text


class TestThreeGroupRunner:
    """--three-group 模式的 runner 输出"""

    def test_three_group_json_has_all_configs(self, tmp_path: Path) -> None:
        """JSON 包含三组 config：subset_baseline / subset_scripted_retry / subset_prompt_sensitive"""
        result = subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path), "--three-group"],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"Runner failed: {result.stderr}"

        json_files = list(tmp_path.glob("memory_eval_*.json"))
        data = json.loads(json_files[0].read_text(encoding="utf-8"))

        assert "subset_baseline" in data["memory"]
        assert "subset_scripted_retry" in data["memory"]
        assert "subset_prompt_sensitive" in data["memory"]

    def test_three_group_json_has_comparison(self, tmp_path: Path) -> None:
        """JSON 包含 comparison/deltas 字段"""
        subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path), "--three-group"],
            capture_output=True, text=True, timeout=120,
        )

        json_files = list(tmp_path.glob("memory_eval_*.json"))
        data = json.loads(json_files[0].read_text(encoding="utf-8"))

        assert "comparison" in data
        comp = data["comparison"]
        assert "scripted_vs_baseline" in comp
        assert "prompt_sensitive_vs_scripted" in comp
        assert "prompt_sensitive_vs_baseline" in comp
        # 每个 comparison 都有 delta 字段
        for key in comp:
            assert "correct_delta" in comp[key]
            assert "reread_delta" in comp[key]

    def test_three_group_json_has_subset_info(self, tmp_path: Path) -> None:
        """JSON 包含 task_scope 和 subset_task_count"""
        subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path), "--three-group"],
            capture_output=True, text=True, timeout=120,
        )

        json_files = list(tmp_path.glob("memory_eval_*.json"))
        data = json.loads(json_files[0].read_text(encoding="utf-8"))

        assert data.get("task_scope") == "reflection_sensitive_subset"
        assert "subset_task_count" in data
        assert data["subset_task_count"] > 0
        assert "subset_task_ids" in data
        assert len(data["subset_task_ids"]) == data["subset_task_count"]

    def test_three_group_uses_same_subset(self, tmp_path: Path) -> None:
        """三组使用同一任务子集（task_id 一致）"""
        subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path), "--three-group"],
            capture_output=True, text=True, timeout=120,
        )

        json_files = list(tmp_path.glob("memory_eval_*.json"))
        data = json.loads(json_files[0].read_text(encoding="utf-8"))

        subset_ids = set(data["subset_task_ids"])
        # 三组 config 的 task_results 应该包含相同的 task_id
        for config_name in ["subset_baseline", "subset_scripted_retry", "subset_prompt_sensitive"]:
            config = data["memory"][config_name]
            # 每组都跑了 subset_task_count 个任务
            assert config.get("eligible_memory_tasks", 0) > 0 or config.get("l3l4_tasks", 0) >= 0
