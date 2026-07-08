"""Patch/File-Edit Benchmark 测试

验证 patch benchmark runner 的核心逻辑：
1. 正确识别 pass/fail
2. 正确处理各种边界场景
3. 指标计算正确
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from scripts.run_patch_benchmark import run_patch_benchmark, _run_task, _create_context


class TestPatchBenchmarkRunner:
    """Patch benchmark runner 集成测试"""

    def test_runner_loads_tasks(self) -> None:
        """runner 能正确加载任务文件"""
        result = run_patch_benchmark("benchmarks/patch_tasks.json")
        assert result["total"] > 0
        assert "pass_rate" in result
        assert "details" in result

    def test_runner_all_tasks_pass(self) -> None:
        """所有任务应该通过（patch benchmark 测的是工具可靠性）"""
        result = run_patch_benchmark("benchmarks/patch_tasks.json")
        # 工具本身应该全部通过
        failed = [d for d in result["details"] if not d["passed"]]
        if failed:
            fail_msg = "\n".join(f"  - {d['task_id']}: {d['error']}" for d in failed)
            pytest.fail(f"Failed tasks:\n{fail_msg}")

    def test_runner_returns_metrics(self) -> None:
        """runner 返回完整的指标"""
        result = run_patch_benchmark("benchmarks/patch_tasks.json")
        assert "edit_pass_rate" in result
        assert "write_pass_rate" in result
        assert "preview_no_write_rate" in result
        assert "invalid_path_block_rate" in result
        assert "unintended_change_count" in result


class TestExactEdit:
    """精确编辑测试"""

    def test_exact_unique_replace(self) -> None:
        with tempfile.TemporaryDirectory() as ws:
            fp = os.path.join(ws, "target.py")
            with open(fp, "w") as f:
                f.write("def hello():\n    print('hello')\n")
            task = {
                "id": "test",
                "operation": "edit",
                "args": {"file_path": fp, "old_string": "print('hello')", "new_string": "print('hi')"},
                "setup": {},
                "expected_success": True,
                "expected_content_contains": ["print('hi')"],
                "expected_content_not_contains": ["print('hello')"],
            }
            result = _run_task(task, ws)
            assert result.passed, result.error

    def test_edit_preserves_surrounding(self) -> None:
        """编辑只改变目标区域"""
        with tempfile.TemporaryDirectory() as ws:
            fp = os.path.join(ws, "target.py")
            content = "line1\nline2\nline3\nline4\nline5\n"
            with open(fp, "w") as f:
                f.write(content)
            task = {
                "id": "test",
                "operation": "edit",
                "args": {"file_path": fp, "old_string": "line3", "new_string": "LINE3"},
                "setup": {},
                "expected_success": True,
                "expected_exact_content": "line1\nline2\nLINE3\nline4\nline5\n",
            }
            result = _run_task(task, ws)
            assert result.passed, result.error


class TestMultiMatch:
    """多匹配场景测试"""

    def test_multi_match_rejected(self) -> None:
        """replace_all=false 时应拒绝多匹配"""
        with tempfile.TemporaryDirectory() as ws:
            fp = os.path.join(ws, "target.py")
            with open(fp, "w") as f:
                f.write("x = 1\ny = 2\nx = 3\n")
            task = {
                "id": "test",
                "operation": "edit",
                "args": {"file_path": fp, "old_string": "x = ", "new_string": "x = 100 "},
                "setup": {},
                "expected_success": False,
                "expected_error_contains": ["匹配多个"],
            }
            result = _run_task(task, ws)
            assert result.passed, result.error

    def test_multi_match_replace_all(self) -> None:
        """replace_all=true 应替换所有匹配"""
        with tempfile.TemporaryDirectory() as ws:
            fp = os.path.join(ws, "target.py")
            with open(fp, "w") as f:
                f.write("x = 1\ny = 2\nx = 3\n")
            task = {
                "id": "test",
                "operation": "edit",
                "args": {"file_path": fp, "old_string": "x = ", "new_string": "x = 100 ", "replace_all": True},
                "setup": {},
                "expected_success": True,
                "expected_content_contains": ["x = 100 1", "x = 100 3"],
            }
            result = _run_task(task, ws)
            assert result.passed, result.error


class TestMissingTarget:
    """目标不存在测试"""

    def test_missing_old_string(self) -> None:
        with tempfile.TemporaryDirectory() as ws:
            fp = os.path.join(ws, "target.py")
            with open(fp, "w") as f:
                f.write("hello world\n")
            task = {
                "id": "test",
                "operation": "edit",
                "args": {"file_path": fp, "old_string": "nonexistent", "new_string": "x"},
                "setup": {},
                "expected_success": False,
            }
            result = _run_task(task, ws)
            assert result.passed, result.error

    def test_nonexistent_file(self) -> None:
        with tempfile.TemporaryDirectory() as ws:
            task = {
                "id": "test",
                "operation": "edit",
                "args": {"file_path": os.path.join(ws, "nope.py"), "old_string": "x", "new_string": "y"},
                "setup": {},
                "expected_success": False,
            }
            result = _run_task(task, ws)
            assert result.passed, result.error


class TestPreviewMode:
    """预览模式测试"""

    def test_preview_no_write(self) -> None:
        """预览模式不应修改文件"""
        with tempfile.TemporaryDirectory() as ws:
            fp = os.path.join(ws, "target.py")
            original = "original content\n"
            with open(fp, "w") as f:
                f.write(original)
            task = {
                "id": "test",
                "operation": "edit",
                "args": {"file_path": fp, "old_string": "original", "new_string": "modified", "preview": True},
                "setup": {},
                "expected_success": True,
                "expected_no_file_change": True,
            }
            result = _run_task(task, ws)
            assert result.passed, result.error


class TestWriteOperations:
    """写入操作测试"""

    def test_write_new_file(self) -> None:
        with tempfile.TemporaryDirectory() as ws:
            task = {
                "id": "test",
                "operation": "write",
                "args": {"file_path": os.path.join(ws, "new.py"), "content": "hello\n"},
                "setup": {},
                "expected_success": True,
                "expected_content_contains": ["hello"],
            }
            result = _run_task(task, ws)
            assert result.passed, result.error

    def test_write_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as ws:
            fp = os.path.join(ws, "existing.py")
            with open(fp, "w") as f:
                f.write("original\n")
            task = {
                "id": "test",
                "operation": "write",
                "args": {"file_path": fp, "content": "new\n"},
                "setup": {},
                "expected_success": False,
            }
            result = _run_task(task, ws)
            assert result.passed, result.error

    def test_write_to_directory_fails(self) -> None:
        with tempfile.TemporaryDirectory() as ws:
            subdir = os.path.join(ws, "subdir")
            os.makedirs(subdir)
            task = {
                "id": "test",
                "operation": "write",
                "args": {"file_path": subdir, "content": "test"},
                "setup": {},
                "expected_success": False,
            }
            result = _run_task(task, ws)
            assert result.passed, result.error


class TestUnicodeAndEdgeCases:
    """Unicode 和边界情况测试"""

    def test_unicode_edit(self) -> None:
        with tempfile.TemporaryDirectory() as ws:
            fp = os.path.join(ws, "unicode.py")
            with open(fp, "w", encoding="utf-8") as f:
                f.write("# 中文注释\nmessage = '你好世界'\n")
            task = {
                "id": "test",
                "operation": "edit",
                "args": {"file_path": fp, "old_string": "你好世界", "new_string": "Hello World"},
                "setup": {},
                "expected_success": True,
                "expected_content_contains": ["Hello World"],
            }
            result = _run_task(task, ws)
            assert result.passed, result.error

    def test_empty_old_string_rejected(self) -> None:
        """空 old_string 应被拒绝（通过验证层或执行层的多匹配检测）"""
        with tempfile.TemporaryDirectory() as ws:
            fp = os.path.join(ws, "target.py")
            with open(fp, "w") as f:
                f.write("hello\n")
            task = {
                "id": "test",
                "operation": "edit",
                "args": {"file_path": fp, "old_string": "", "new_string": "x"},
                "setup": {},
                "expected_success": False,
                "expected_error_contains": ["old_string", "匹配多个"],
            }
            result = _run_task(task, ws)
            assert result.passed, result.error
