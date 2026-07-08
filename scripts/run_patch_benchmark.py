"""Patch/File-Edit Benchmark Runner — 直接测试 file_edit/file_write 工具链可靠性。

不通过 AgentLoop，直接调用工具函数，验证文件编辑的各种边界场景。

用法:
    uv run python scripts/run_patch_benchmark.py
    uv run python scripts/run_patch_benchmark.py --tasks benchmarks/patch_tasks.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 确保 src 在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.core.context import ToolUseContext, AbortController, FileReadState
from agent.tools.file_edit import execute_file_edit
from agent.tools.file_write import execute_file_write


@dataclass
class PatchTaskResult:
    """单个 patch 任务结果"""
    task_id: str
    passed: bool
    expected_success: bool
    actual_success: bool
    error: str = ""
    details: str = ""


def _create_context(workspace: str) -> ToolUseContext:
    """创建工具执行上下文"""
    return ToolUseContext(
        model="test",
        tools=[],
        abort_controller=AbortController(),
        file_read_state=FileReadState(),
        messages=[],
        debug=False,
        verbose=False,
        cwd=workspace,
        agent_loop=None,
    )


def _generate_large_content() -> str:
    """生成大文件内容（约 100KB），包含唯一标记"""
    lines = [f"# Line {i}: {'x' * 80}" for i in range(1000)]
    lines[500] = "# MARKER_UNIQUE_12345"
    return "\n".join(lines) + "\n"


def _run_task(task: dict[str, Any], workspace: str) -> PatchTaskResult:
    """执行单个 patch 任务"""
    task_id = task["id"]
    operation = task["operation"]
    args = dict(task.get("args", {}))
    setup = task.get("setup", {})
    expected_success = task.get("expected_success", True)

    context = _create_context(workspace)

    # Setup: 创建文件/目录
    original_content = None
    if setup:
        if "file" in setup:
            file_path = os.path.join(workspace, setup["file"])
            if "content_generator" in setup and setup["content_generator"] == "large":
                content = _generate_large_content()
            else:
                content = setup.get("content", "")
            os.makedirs(os.path.dirname(file_path) or workspace, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            original_content = content
        if "dir" in setup:
            dir_path = os.path.join(workspace, setup["dir"])
            os.makedirs(dir_path, exist_ok=True)

    # 解析 file_path 为绝对路径
    if "file_path" in args:
        fp = args["file_path"]
        if not os.path.isabs(fp):
            args["file_path"] = os.path.join(workspace, fp)

    # 执行操作
    result = None
    try:
        if operation == "edit":
            result = execute_file_edit(args, context)
        elif operation == "write":
            result = execute_file_write(args, context)
        else:
            return PatchTaskResult(
                task_id=task_id,
                passed=False,
                expected_success=expected_success,
                actual_success=False,
                error=f"Unknown operation: {operation}",
            )
    except Exception as e:
        return PatchTaskResult(
            task_id=task_id,
            passed=False,
            expected_success=expected_success,
            actual_success=False,
            error=f"Exception: {e}",
        )

    actual_success = not result.is_error

    # 检查期望
    if actual_success != expected_success:
        return PatchTaskResult(
            task_id=task_id,
            passed=False,
            expected_success=expected_success,
            actual_success=actual_success,
            error=f"Expected success={expected_success}, got {actual_success}. Output: {result.output[:200]}",
        )

    # 如果期望失败，检查错误信息
    if not expected_success:
        error_contains = task.get("expected_error_contains", [])
        if error_contains:
            output_lower = str(result.output).lower()
            matched = any(ec.lower() in output_lower for ec in error_contains)
            if not matched:
                return PatchTaskResult(
                    task_id=task_id,
                    passed=False,
                    expected_success=expected_success,
                    actual_success=actual_success,
                    error=f"Expected error to contain {error_contains}, got: {result.output[:200]}",
                )
        return PatchTaskResult(
            task_id=task_id,
            passed=True,
            expected_success=expected_success,
            actual_success=actual_success,
            details=f"Correctly failed: {result.output[:100]}",
        )

    # 成功情况：检查文件内容
    file_path = args.get("file_path", "")
    if file_path and os.path.isfile(file_path):
        with open(file_path, encoding="utf-8") as f:
            actual_content = f.read()

        # 检查 expected_content_contains
        for expected in task.get("expected_content_contains", []):
            if expected not in actual_content:
                return PatchTaskResult(
                    task_id=task_id,
                    passed=False,
                    expected_success=expected_success,
                    actual_success=actual_success,
                    error=f"Content does not contain '{expected}'",
                )

        # 检查 expected_content_not_contains
        for not_expected in task.get("expected_content_not_contains", []):
            if not_expected in actual_content:
                return PatchTaskResult(
                    task_id=task_id,
                    passed=False,
                    expected_success=expected_success,
                    actual_success=actual_success,
                    error=f"Content should not contain '{not_expected}'",
                )

        # 检查 expected_exact_content
        if "expected_exact_content" in task:
            if actual_content != task["expected_exact_content"]:
                return PatchTaskResult(
                    task_id=task_id,
                    passed=False,
                    expected_success=expected_success,
                    actual_success=actual_success,
                    error=f"Content mismatch. Expected:\n{task['expected_exact_content'][:200]}\nGot:\n{actual_content[:200]}",
                )

        # 检查 expected_no_file_change
        if task.get("expected_no_file_change") and original_content is not None:
            if actual_content != original_content:
                return PatchTaskResult(
                    task_id=task_id,
                    passed=False,
                    expected_success=expected_success,
                    actual_success=actual_success,
                    error="File was modified in preview mode",
                )

    # 检查 diff 内容
    if "expected_diff_contains" in task and result.output:
        for diff_part in task["expected_diff_contains"]:
            if diff_part not in str(result.output):
                return PatchTaskResult(
                    task_id=task_id,
                    passed=False,
                    expected_success=expected_success,
                    actual_success=actual_success,
                    error=f"Diff does not contain '{diff_part}'",
                )

    return PatchTaskResult(
        task_id=task_id,
        passed=True,
        expected_success=expected_success,
        actual_success=actual_success,
        details="All checks passed",
    )


def run_patch_benchmark(
    tasks_path: str = "benchmarks/patch_tasks.json",
) -> dict[str, Any]:
    """运行 patch/file-edit benchmark

    Args:
        tasks_path: 任务文件路径

    Returns:
        结果字典
    """
    print(f"Loading tasks: {tasks_path}")
    with open(tasks_path, encoding="utf-8") as f:
        data = json.load(f)

    tasks = data["tasks"]
    print(f"Loaded {len(tasks)} tasks\n")

    results: list[PatchTaskResult] = []

    for task in tasks:
        # 创建临时工作区
        with tempfile.TemporaryDirectory(prefix="patch_bench_") as workspace:
            print(f"  {task['id']:35s} ... ", end="", flush=True)
            result = _run_task(task, workspace)
            status = "PASS" if result.passed else "FAIL"
            print(f"{status}  {result.details or result.error}")
            results.append(result)

    # 计算指标
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    pass_rate = passed / total if total > 0 else 0.0

    # 分类统计
    edit_tasks = [r for r in results if r.task_id in [
        "exact_unique_replace", "multi_match_reject", "multi_match_replace_all",
        "missing_target_string", "preview_no_write", "edit_nonexistent_file",
        "edit_empty_old_string", "diff_correctness", "large_file_edit",
        "unicode_content", "edit_preserves_surrounding",
    ]]
    write_tasks = [r for r in results if r.task_id in [
        "atomic_write_new_file", "write_no_overwrite", "write_with_overwrite",
        "write_to_directory",
    ]]

    edit_passed = sum(1 for r in edit_tasks if r.passed)
    write_passed = sum(1 for r in write_tasks if r.passed)

    # 高级指标
    preview_tasks = [r for r in results if "preview" in r.task_id]
    preview_ok = sum(1 for r in preview_tasks if r.passed)

    # invalid_path: 测试写入目录等非法目标（注：不包含 PathGuard 的 .. 逃逸检测，
    # 因为 edit/write 原语不包含路径边界检查，那是 loop 层 PathGuard 的职责）
    invalid_path_tasks = [r for r in results if r.task_id in ("write_to_directory",)]
    invalid_path_blocked = sum(1 for r in invalid_path_tasks if r.passed and not r.actual_success)

    unintended_changes = 0
    for r in results:
        if "preserves" in r.task_id and not r.passed:
            unintended_changes += 1

    print("\n" + "=" * 60)
    print("PATCH BENCHMARK RESULTS")
    print("=" * 60)
    print(f"Total tasks:     {total}")
    print(f"Passed:          {passed}")
    print(f"Pass rate:       {pass_rate:.1%}")
    print()
    print(f"Edit tasks:      {edit_passed}/{len(edit_tasks)} passed")
    print(f"Write tasks:     {write_passed}/{len(write_tasks)} passed")
    print(f"Preview no-write: {preview_ok}/{len(preview_tasks)} passed")
    print(f"Invalid path block: {invalid_path_blocked}/{len(invalid_path_tasks)} blocked")
    print()

    print("Per-task breakdown:")
    print("-" * 60)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        detail = r.error if r.error else r.details
        print(f"  {r.task_id:35s} {status}  {detail[:50]}")

    return {
        "total": total,
        "passed": passed,
        "pass_rate": pass_rate,
        "edit_pass_rate": edit_passed / len(edit_tasks) if edit_tasks else 0.0,
        "write_pass_rate": write_passed / len(write_tasks) if write_tasks else 0.0,
        "preview_no_write_rate": preview_ok / len(preview_tasks) if preview_tasks else 0.0,
        "invalid_path_block_rate": invalid_path_blocked / len(invalid_path_tasks) if invalid_path_tasks else 0.0,
        "unintended_change_count": unintended_changes,
        "details": [
            {"task_id": r.task_id, "passed": r.passed, "error": r.error, "details": r.details}
            for r in results
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run patch/file-edit benchmark")
    parser.add_argument(
        "--tasks",
        default="benchmarks/patch_tasks.json",
        help="Path to tasks file",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file path",
    )
    args = parser.parse_args()

    result = run_patch_benchmark(args.tasks)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nResults saved to: {output_path}")

    sys.exit(0 if result["pass_rate"] == 1.0 else 1)


if __name__ == "__main__":
    main()
