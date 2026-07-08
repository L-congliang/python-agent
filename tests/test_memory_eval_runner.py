"""测试 Phase 3.2E Memory Eval Runner"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


class TestMemoryEvalRunner:
    """测试 memory eval runner 的输出"""

    def test_runner_produces_json_and_md(self, tmp_path: Path) -> None:
        """runner 输出 JSON 和 Markdown 文件"""
        result = subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path)],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"Runner failed: {result.stderr}"

        # 检查输出文件存在
        json_files = list(tmp_path.glob("memory_eval_*.json"))
        md_files = list(tmp_path.glob("memory_eval_*.md"))
        assert len(json_files) == 1, f"Expected 1 JSON file, got {len(json_files)}"
        assert len(md_files) == 1, f"Expected 1 MD file, got {len(md_files)}"

    def test_json_schema_stable(self, tmp_path: Path) -> None:
        """JSON 输出 schema 稳定"""
        subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path)],
            capture_output=True, text=True, timeout=120,
        )

        json_files = list(tmp_path.glob("memory_eval_*.json"))
        data = json.loads(json_files[0].read_text(encoding="utf-8"))

        # 顶层字段
        assert "run_id" in data
        assert "timestamp" in data
        assert "task_count" in data
        assert "memory" in data

        # 三组配置都在
        assert "memory_on" in data["memory"]
        assert "memory_off" in data["memory"]
        assert "memory_irrelevant" in data["memory"]

        # 每组都有所有指标
        for config_name in ["memory_on", "memory_off", "memory_irrelevant"]:
            config = data["memory"][config_name]
            assert "correct_rate" in config
            assert "memory_dependent_success_rate" in config
            assert "target_reread_rate" in config
            assert "answer_without_reread_rate" in config
            assert "avg_tool_calls" in config
            assert "avg_duration" in config
            assert "memory_hit_rate" in config
            assert "repeated_reads" in config

    def test_memory_irrelevant_in_output(self, tmp_path: Path) -> None:
        """memory_irrelevant 被纳入正式输出"""
        subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path)],
            capture_output=True, text=True, timeout=120,
        )

        json_files = list(tmp_path.glob("memory_eval_*.json"))
        data = json.loads(json_files[0].read_text(encoding="utf-8"))

        irr = data["memory"]["memory_irrelevant"]
        assert isinstance(irr["correct_rate"], (int, float))
        assert isinstance(irr["avg_tool_calls"], (int, float))

    def test_runner_works_without_api_key(self, tmp_path: Path) -> None:
        """不需要真实 API key 就能运行（MIMO_API_KEY 未设置也不报错）"""
        import os
        # 保存原始值
        old_key = os.environ.pop("MIMO_API_KEY", None)
        try:
            result = subprocess.run(
                [sys.executable, "scripts/run_phase32_memory_eval.py",
                 "--output-dir", str(tmp_path)],
                capture_output=True, text=True, timeout=120,
            )
            assert result.returncode == 0, f"Runner failed: {result.stderr}"
        finally:
            # 恢复原始值
            if old_key is not None:
                os.environ["MIMO_API_KEY"] = old_key

    def test_markdown_report_has_sections(self, tmp_path: Path) -> None:
        """Markdown 报告包含必要章节"""
        subprocess.run(
            [sys.executable, "scripts/run_phase32_memory_eval.py",
             "--output-dir", str(tmp_path)],
            capture_output=True, text=True, timeout=120,
        )

        md_files = list(tmp_path.glob("memory_eval_*.md"))
        content = md_files[0].read_text(encoding="utf-8")

        assert "# Memory Experiment Report" in content
        assert "memory_on" in content
        assert "memory_off" in content
        assert "memory_irrelevant" in content
