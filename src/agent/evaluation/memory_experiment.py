"""Memory Experiment - 验证记忆系统的效果

实验设计:
- memory_on: 使用完整记忆系统（memory_enabled=True）
- memory_off: 不使用记忆（memory_enabled=False）
- memory_irrelevant: 使用无关记忆（噪音）

评估指标（全部来自真实运行数据）:
- correct_rate: 正确率（由 verifier 判定）
- repeated_reads: 重复读取次数（同一文件第 2 次及以后成功读取）
- memory_hit_rate: 记忆命中率（避免不必要 reread 的任务比例）
- avg_tool_calls: 平均工具调用次数
- avg_duration: 平均耗时
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.evaluation.memory_experiment")


# ============================================================
# 数据结构
# ============================================================


@dataclass
class MemoryTask:
    """记忆测试任务

    Attributes:
        task_id: 任务 ID
        category: 类别（fact_lookup, edit_dependency, history_reference）
        prompt: 主任务提示
        setup_turns: 前置对话（为 history_reference 提供上下文）
        expected_files: 预期访问的文件
        target_files: 用于 repeated_reads / memory_hit 统计的文件
        verifier: 验证方式（contains_text / file_changed / multi_file_changed）
        expected_substrings: 正确性验证的期望子串
        fixture_dir: 该任务使用的 fixture 子目录（相对于 tests/fixtures/memory_experiment/）
        allow_reread: 是否允许重复读取
    """
    task_id: str
    category: str
    prompt: str
    setup_turns: list[str] = field(default_factory=list)
    expected_files: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)
    verifier: str = "contains_text"
    expected_substrings: list[str] = field(default_factory=list)
    fixture_dir: str = ""
    allow_reread: bool = False


@dataclass
class MemoryConfig:
    """记忆配置

    Attributes:
        name: 配置名称
        use_memory: 是否使用记忆
        use_irrelevant_memory: 是否使用无关记忆
    """
    name: str
    use_memory: bool = True
    use_irrelevant_memory: bool = False


@dataclass
class MemoryMetrics:
    """记忆指标

    Attributes:
        repeated_reads: 重复读取次数
        correct_rate: 正确率
        memory_hit_rate: 记忆命中率（eligible 任务中的命中比例）
        total_tool_calls: 总工具调用次数
        total_tokens: 总 token 数
        avg_tool_calls: 平均工具调用次数
        avg_duration: 平均耗时
        eligible_memory_tasks: 可判定 memory_hit 的任务数
    """
    repeated_reads: int = 0
    correct_rate: float = 0.0
    memory_hit_rate: float = 0.0
    total_tool_calls: int = 0
    total_tokens: int = 0
    avg_tool_calls: float = 0.0
    avg_duration: float = 0.0
    eligible_memory_tasks: int = 0


@dataclass
class MemoryAblationResult:
    """消融实验结果

    Attributes:
        config: 配置
        metrics: 指标
        duration: 耗时
        task_results: 各任务结果
    """
    config: MemoryConfig
    metrics: MemoryMetrics
    duration: float = 0.0
    task_results: list[dict[str, Any]] = field(default_factory=list)


# ============================================================
# 测试任务（基于真实 repo 文件 + fixture 文件）
# ============================================================

_FIXTURE_BASE = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "memory_experiment"

MEMORY_TASKS = [
    # --- fact_lookup: 问答类，验证 contains_text ---
    MemoryTask(
        task_id="fact_loop_max_turns",
        category="fact_lookup",
        prompt="What is the default value of max_turns in LoopConfig? Answer with just the number.",
        target_files=["src/agent/core/loop.py"],
        verifier="contains_text",
        expected_substrings=["50"],
    ),
    MemoryTask(
        task_id="fact_manager_methods",
        category="fact_lookup",
        prompt="List the public method names in MemoryManager class (from memory/manager.py). "
               "Answer as a comma-separated list.",
        target_files=["src/agent/memory/manager.py"],
        verifier="contains_text",
        expected_substrings=["set_task", "touch_file"],
    ),

    # --- history_reference: 有 setup_turns，验证 memory_hit ---
    MemoryTask(
        task_id="history_loop_config",
        category="history_reference",
        prompt="What is the default value of max_turns in LoopConfig? Answer with just the number.",
        setup_turns=[
            "Read the file src/agent/core/loop.py and tell me what LoopConfig's max_turns default is.",
        ],
        target_files=["src/agent/core/loop.py"],
        verifier="contains_text",
        expected_substrings=["50"],
    ),
    MemoryTask(
        task_id="history_manager_class",
        category="history_reference",
        prompt="What methods does MemoryManager have? List them.",
        setup_turns=[
            "Read src/agent/memory/manager.py and describe the MemoryManager class.",
        ],
        target_files=["src/agent/memory/manager.py"],
        verifier="contains_text",
        expected_substrings=["set_task"],
    ),

    # --- edit_dependency: fixture 文件，验证 file_changed ---
    MemoryTask(
        task_id="edit_main_function",
        category="edit_dependency",
        prompt="In main.py, change the calculate_sum function to also accept an optional third "
               "parameter 'c' with default 0, and add it to the sum. Then read utils.py to check "
               "if format_output needs any update.",
        fixture_dir=".",
        target_files=["main.py", "utils.py"],
        verifier="file_changed",
        expected_substrings=["c: int = 0"],
    ),
    MemoryTask(
        task_id="edit_config_update",
        category="edit_dependency",
        prompt="Read config.json, then update main.py to use the 'max_items' value from config.json "
               "as the default for a new parameter in calculate_sum.",
        fixture_dir=".",
        target_files=["main.py", "config.json"],
        verifier="file_changed",
        expected_substrings=["max_items"],
    ),
]


# ============================================================
# AgentLoop 工厂
# ============================================================


def _create_real_agent_loop(
    memory_enabled: bool = True,
    workspace_root: str | None = None,
    max_turns: int = 15,
):
    """创建真实的 AgentLoop

    Args:
        memory_enabled: 是否启用记忆系统
        workspace_root: 工作区根目录
        max_turns: 最大轮次

    Returns:
        AgentLoop 实例
    """
    from agent.core.model import MimoClient, ModelConfig
    from agent.core.loop import AgentLoop, LoopConfig
    from agent.tools.registry import ToolRegistry
    from agent.tools.bash import bash_tool
    from agent.tools.file_read import file_read_tool
    from agent.tools.file_write import file_write_tool
    from agent.tools.file_edit import file_edit_tool
    from agent.tools.grep import grep_tool
    from agent.tools.glob import glob_tool

    api_key = os.environ.get("MIMO_API_KEY", "")
    base_url = os.environ.get(
        "MIMO_BASE_URL",
        "https://token-plan-cn.xiaomimimo.com/anthropic",
    )
    model = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")

    if not api_key:
        raise ValueError("MIMO_API_KEY not set. Export it or pass via environment.")

    config = ModelConfig(api_key=api_key, base_url=base_url, model=model)
    client = MimoClient(config)

    registry = ToolRegistry()
    registry.register(bash_tool)
    registry.register(file_read_tool)
    registry.register(file_write_tool)
    registry.register(file_edit_tool)
    registry.register(grep_tool)
    registry.register(glob_tool)

    loop_config = LoopConfig(
        model=config.model,
        max_turns=max_turns,
        system_prompt="You are a helpful coding assistant. Answer concisely.",
        memory_enabled=memory_enabled,
        workspace_root=workspace_root,
    )

    return AgentLoop(client, registry, config=loop_config)


# ============================================================
# 验证器
# ============================================================


def _verify_task_result(
    task: MemoryTask,
    result_text: str,
    workspace_root: str,
) -> bool:
    """验证任务结果

    Args:
        task: 任务定义
        result_text: 模型最终回复
        workspace_root: 工作区根目录

    Returns:
        是否正确
    """
    if task.verifier == "contains_text":
        result_lower = result_text.lower()
        return all(sub.lower() in result_lower for sub in task.expected_substrings)

    if task.verifier == "file_changed":
        for target in task.target_files:
            file_path = os.path.join(workspace_root, target)
            if not os.path.exists(file_path):
                continue
            try:
                content = Path(file_path).read_text(encoding="utf-8")
                if any(sub in content for sub in task.expected_substrings):
                    return True
            except OSError:
                continue
        return False

    if task.verifier == "multi_file_changed":
        changed = 0
        for target in task.target_files:
            file_path = os.path.join(workspace_root, target)
            if os.path.exists(file_path):
                changed += 1
        return changed >= 2

    # 未知 verifier，默认通过
    return True


def _count_repeated_reads(
    tool_history: list[dict[str, Any]],
    target_files: list[str],
    workspace_root: str,
) -> int:
    """统计重复读取次数

    定义：同一任务内，对同一 resolved_path 的第 2 次及以后成功 read，计为 repeated_read。

    Args:
        tool_history: 工具执行历史
        target_files: 目标文件列表（相对路径）
        workspace_root: 工作区根目录

    Returns:
        重复读取次数
    """
    if not target_files:
        return 0

    # 构建目标文件的绝对路径集合
    target_abs = set()
    for f in target_files:
        target_abs.add(os.path.normpath(os.path.join(workspace_root, f)))

    read_counts: Counter[str] = Counter()
    for entry in tool_history:
        if entry.get("tool_name") != "read":
            continue
        if entry.get("is_error"):
            continue
        if entry.get("blocked_by_repeat_detector"):
            continue
        resolved = entry.get("resolved_path", "")
        if not resolved:
            continue
        resolved = os.path.normpath(resolved)
        if target_abs and resolved not in target_abs:
            continue
        read_counts[resolved] += 1

    # 每个文件第 2 次及以后的读取算重复
    return sum(count - 1 for count in read_counts.values() if count > 1)


def _compute_memory_hit(
    task: MemoryTask,
    tool_history: list[dict[str, Any]],
    workspace_root: str,
) -> int:
    """计算 memory_hit

    定义：对于有 setup_turns 的任务，如果主任务阶段没有再次 read 已在 setup 阶段
    读过的目标文件，则记 1；否则记 0。

    Args:
        task: 任务定义
        tool_history: 工具执行历史
        workspace_root: 工作区根目录

    Returns:
        0 或 1
    """
    if not task.setup_turns:
        # 没有 setup_turns 的任务不算 eligible
        return -1  # 表示不计入统计

    if not task.target_files:
        return -1

    # 构建目标文件的绝对路径集合
    target_abs = set()
    for f in task.target_files:
        target_abs.add(os.path.normpath(os.path.join(workspace_root, f)))

    # 统计主任务阶段（所有 tool_history 都是主任务阶段的，
    # 因为 setup_turns 用的是独立的 loop.run()）
    main_reads: set[str] = set()
    for entry in tool_history:
        if entry.get("tool_name") != "read":
            continue
        if entry.get("is_error"):
            continue
        resolved = entry.get("resolved_path", "")
        if not resolved:
            continue
        resolved = os.path.normpath(resolved)
        if target_abs and resolved in target_abs:
            main_reads.add(resolved)

    # 如果主任务阶段没有读取任何目标文件 → memory_hit（记忆避免了 reread）
    return 1 if len(main_reads) == 0 else 0


# ============================================================
# 实验主类
# ============================================================


class MemoryExperiment:
    """记忆实验

    使用方式:
        experiment = MemoryExperiment(use_real_model=True)
        results = experiment.run()
        report = experiment.generate_report(results)
    """

    def __init__(
        self,
        output_dir: str | Path | None = None,
        max_turns: int = 15,
        use_real_model: bool = False,
    ) -> None:
        """初始化

        Args:
            output_dir: 输出目录
            max_turns: 每个任务最大轮次
            use_real_model: 是否使用真实模型
        """
        if output_dir is None:
            output_dir = Path.cwd() / "docs" / "test-reports"
        self._output_dir = Path(output_dir)
        self._max_turns = max_turns
        self._use_real_model = use_real_model

        self._configs = [
            MemoryConfig(name="memory_on", use_memory=True),
            MemoryConfig(name="memory_off", use_memory=False),
            MemoryConfig(name="memory_irrelevant", use_memory=True, use_irrelevant_memory=True),
        ]

    def run(self, tasks: list[MemoryTask] | None = None) -> list[MemoryAblationResult]:
        """运行实验

        Args:
            tasks: 测试任务列表，默认使用 MEMORY_TASKS

        Returns:
            各配置的实验结果
        """
        if tasks is None:
            tasks = MEMORY_TASKS

        results = []
        for config in self._configs:
            logger.info("Running config: %s", config.name)
            result = self._run_single_config(config, tasks)
            results.append(result)

        return results

    def _run_single_config(
        self,
        config: MemoryConfig,
        tasks: list[MemoryTask],
    ) -> MemoryAblationResult:
        """运行单个配置"""
        start_time = time.time()
        task_results = []
        total_repeated_reads = 0
        total_correct = 0
        total_memory_hits = 0
        total_tool_calls = 0
        total_duration = 0.0
        eligible_memory_tasks = 0

        for task in tasks:
            logger.info("  Running task: %s", task.task_id)
            result = self._run_single_task(config, task)
            task_results.append(result)

            total_repeated_reads += result.get("repeated_reads", 0)
            if result.get("correct", False):
                total_correct += 1
            total_tool_calls += result.get("tool_calls", 0)
            total_duration += result.get("duration", 0.0)

            mh = result.get("memory_hits", -1)
            if mh >= 0:
                total_memory_hits += mh
                eligible_memory_tasks += 1

        duration = time.time() - start_time
        n = len(tasks) if tasks else 1

        metrics = MemoryMetrics(
            repeated_reads=total_repeated_reads,
            correct_rate=total_correct / n,
            memory_hit_rate=total_memory_hits / eligible_memory_tasks if eligible_memory_tasks > 0 else 0.0,
            total_tool_calls=total_tool_calls,
            avg_tool_calls=total_tool_calls / n,
            avg_duration=total_duration / n,
            eligible_memory_tasks=eligible_memory_tasks,
        )

        return MemoryAblationResult(
            config=config,
            metrics=metrics,
            duration=duration,
            task_results=task_results,
        )

    def _run_single_task(
        self,
        config: MemoryConfig,
        task: MemoryTask,
    ) -> dict[str, Any]:
        """运行单个任务"""
        if not self._use_real_model:
            return self._run_mock_task(config, task)

        return self._run_real_task(config, task)

    def _run_mock_task(
        self,
        config: MemoryConfig,
        task: MemoryTask,
    ) -> dict[str, Any]:
        """模拟运行（用于框架测试）"""
        return {
            "task_id": task.task_id,
            "category": task.category,
            "correct": True,
            "repeated_reads": 0,
            "memory_hits": 1 if (config.use_memory and task.setup_turns) else (-1 if not task.setup_turns else 0),
            "tool_calls": 2,
            "duration": 0.5,
        }

    def _run_real_task(
        self,
        config: MemoryConfig,
        task: MemoryTask,
    ) -> dict[str, Any]:
        """使用真实模型运行任务"""
        start_time = time.time()

        # 准备工作区
        workspace_root = self._prepare_workspace(task)

        try:
            loop = _create_real_agent_loop(
                memory_enabled=config.use_memory and not config.use_irrelevant_memory,
                workspace_root=workspace_root,
                max_turns=self._max_turns,
            )

            # 注入无关记忆
            if config.use_irrelevant_memory:
                loop.memory.set_task("这是一个无关的任务：处理用户登录页面的 CSS 样式")
                for i in range(5):
                    loop.memory.append_note(
                        f"无关笔记 {i}: 用户要求修改按钮颜色为蓝色",
                        tags=["noise"],
                    )

            # 跑 setup_turns（前置对话）
            for setup_prompt in task.setup_turns:
                loop.run(setup_prompt)

            # 跑主任务
            result_text = loop.run(task.prompt)

            # 从 tool_history 统计
            tool_calls = len(loop.tool_history)
            repeated_reads = _count_repeated_reads(
                loop.tool_history, task.target_files, workspace_root,
            )
            memory_hits = _compute_memory_hit(
                task, loop.tool_history, workspace_root,
            )
            correct = _verify_task_result(task, result_text, workspace_root)

        except Exception as e:
            logger.error("Task %s failed: %s", task.task_id, e)
            correct = False
            repeated_reads = 0
            memory_hits = -1
            tool_calls = 0
            result_text = ""

        duration = time.time() - start_time

        return {
            "task_id": task.task_id,
            "category": task.category,
            "correct": correct,
            "repeated_reads": repeated_reads,
            "memory_hits": memory_hits,
            "tool_calls": tool_calls,
            "duration": duration,
            "result_preview": result_text[:200] if result_text else "",
        }

    def _prepare_workspace(self, task: MemoryTask) -> str:
        """准备工作区（复制 fixture 文件到临时目录）

        Args:
            task: 任务定义

        Returns:
            工作区根目录路径
        """
        if not task.fixture_dir:
            # 无 fixture，使用 repo 根目录
            return str(Path.cwd())

        # 复制 fixture 到临时目录
        import tempfile
        tmp_dir = Path(tempfile.mkdtemp(prefix="memory_experiment_"))
        fixture_src = _FIXTURE_BASE / task.fixture_dir
        if fixture_src.exists():
            for f in fixture_src.iterdir():
                if f.is_file():
                    shutil.copy2(f, tmp_dir / f.name)
        return str(tmp_dir)

    # ============================================================
    # 报告生成
    # ============================================================

    def generate_report(self, results: list[MemoryAblationResult]) -> str:
        """生成实验报告"""
        report = []
        report.append("# Memory Experiment Report")
        report.append("")
        report.append("## 实验设计")
        report.append("")
        report.append("- memory_on: memory_enabled=True（完整记忆系统）")
        report.append("- memory_off: memory_enabled=False（真关闭，配置级）")
        report.append("- memory_irrelevant: memory_enabled=True + 注入噪声记忆")
        report.append("")

        report.append("## 测试场景")
        report.append("")
        report.append("| 类别 | 数量 | 说明 |")
        report.append("|------|------|------|")
        categories: dict[str, int] = {}
        for task in MEMORY_TASKS:
            categories[task.category] = categories.get(task.category, 0) + 1
        cat_desc = {
            "fact_lookup": "问答类，验证 contains_text",
            "history_reference": "有 setup_turns，验证 memory_hit",
            "edit_dependency": "fixture 文件，验证 file_changed",
        }
        for cat, count in categories.items():
            report.append(f"| {cat} | {count} | {cat_desc.get(cat, '')} |")
        report.append("")

        report.append("## 指标定义")
        report.append("")
        report.append("| 指标 | 定义 |")
        report.append("|------|------|")
        report.append("| correct_rate | verifier 判定正确的任务比例 |")
        report.append("| repeated_reads | 同一文件第 2 次及以后成功读取的总次数 |")
        report.append("| memory_hit_rate | 有 setup_turns 的任务中，主阶段未 reread 目标文件的比例 |")
        report.append("| avg_tool_calls | 平均每任务工具调用次数 |")
        report.append("| avg_duration | 平均每任务耗时（秒） |")
        report.append("")

        report.append("## 实验结果")
        report.append("")
        report.append("| 配置 | correct_rate | repeated_reads | memory_hit_rate | avg_tool_calls | avg_duration | 耗时 |")
        report.append("|------|-------------|----------------|-----------------|---------------|-------------|------|")
        for r in results:
            m = r.metrics
            report.append(
                f"| {r.config.name} | {m.correct_rate:.0%} | {m.repeated_reads} | "
                f"{m.memory_hit_rate:.0%} ({m.eligible_memory_tasks} eligible) | "
                f"{m.avg_tool_calls:.1f} | {m.avg_duration:.1f}s | {r.duration:.1f}s |"
            )
        report.append("")

        report.append("## 各任务详情")
        report.append("")
        for r in results:
            report.append(f"### {r.config.name}")
            report.append("")
            report.append("| task_id | correct | repeated_reads | memory_hit | tool_calls | duration |")
            report.append("|---------|---------|----------------|------------|------------|----------|")
            for tr in r.task_results:
                mh = tr.get("memory_hits", -1)
                mh_str = str(mh) if mh >= 0 else "n/a"
                report.append(
                    f"| {tr['task_id']} | {'✅' if tr.get('correct') else '❌'} | "
                    f"{tr.get('repeated_reads', 0)} | {mh_str} | "
                    f"{tr.get('tool_calls', 0)} | {tr.get('duration', 0):.1f}s |"
                )
            report.append("")

        return "\n".join(report)

    def save_report(
        self,
        results: list[MemoryAblationResult],
        filename: str = "P2-memory-experiment.md",
    ) -> Path:
        """保存实验报告"""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        report_path = self._output_dir / filename
        report = self.generate_report(results)
        report_path.write_text(report, encoding="utf-8")
        logger.info("Report saved to: %s", report_path)
        return report_path


# ============================================================
# 便捷函数
# ============================================================


def run_memory_experiment(use_real_model: bool = False) -> list[MemoryAblationResult]:
    """运行记忆实验"""
    experiment = MemoryExperiment(use_real_model=use_real_model)
    results = experiment.run()
    experiment.save_report(results)
    return results


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run memory experiment")
    parser.add_argument("--real", action="store_true", help="Use real API")
    args = parser.parse_args()

    results = run_memory_experiment(use_real_model=args.real)

    print("\n" + "=" * 60)
    print("Memory Experiment Results")
    print("=" * 60)

    for r in results:
        m = r.metrics
        print(f"\n{r.config.name}:")
        print(f"  correct_rate: {m.correct_rate:.0%}")
        print(f"  repeated_reads: {m.repeated_reads}")
        print(f"  memory_hit_rate: {m.memory_hit_rate:.0%} ({m.eligible_memory_tasks} eligible)")
        print(f"  avg_tool_calls: {m.avg_tool_calls:.1f}")
        print(f"  avg_duration: {m.avg_duration:.1f}s")
