"""Memory Experiment - 验证记忆系统的效果

实验设计:
- memory_on: 使用完整记忆系统
- memory_off: 不使用记忆
- memory_irrelevant: 使用无关记忆（噪音）

测试场景:
- fact_lookup: 查找之前提到的事实
- edit_dependency: 编辑依赖关系（改了 A 文件，需要记住 B 文件也受影响）
- history_reference: 引用历史对话内容

评估指标:
- repeated_reads: 重复读取次数（越少越好）
- correct_rate: 正确率
- memory_hit_rate: 记忆命中率
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.evaluation.memory_experiment")


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
        memory_hit_rate: 记忆命中率
        total_tool_calls: 总工具调用次数
        total_tokens: 总 token 数
    """
    repeated_reads: int = 0
    correct_rate: float = 0.0
    memory_hit_rate: float = 0.0
    total_tool_calls: int = 0
    total_tokens: int = 0


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


@dataclass
class MemoryTask:
    """记忆测试任务

    Attributes:
        task_id: 任务 ID
        category: 类别（fact_lookup, edit_dependency, history_reference）
        prompt: 任务提示
        expected_files: 预期访问的文件
        expected_answer: 预期答案
    """
    task_id: str
    category: str
    prompt: str
    expected_files: list[str] = field(default_factory=list)
    expected_answer: str = ""


# 标准测试任务
MEMORY_TASKS = [
    # fact_lookup: 查找之前提到的事实
    MemoryTask(
        task_id="fact_1",
        category="fact_lookup",
        prompt="What is the function name defined in src/main.py?",
        expected_files=["src/main.py"],
        expected_answer="main",
    ),
    MemoryTask(
        task_id="fact_2",
        category="fact_lookup",
        prompt="What is the import statement at the top of src/utils.py?",
        expected_files=["src/utils.py"],
        expected_answer="import os",
    ),
    # edit_dependency: 编辑依赖关系
    MemoryTask(
        task_id="edit_1",
        category="edit_dependency",
        prompt="Read src/main.py and src/utils.py, then modify the function in main.py. After that, check if utils.py needs any changes.",
        expected_files=["src/main.py", "src/utils.py"],
        expected_answer="both files modified",
    ),
    MemoryTask(
        task_id="edit_2",
        category="edit_dependency",
        prompt="First read config.json, then update settings.py based on the config values.",
        expected_files=["config.json", "settings.py"],
        expected_answer="settings updated",
    ),
    # history_reference: 引用历史对话内容
    MemoryTask(
        task_id="history_1",
        category="history_reference",
        prompt="Remember the file path I mentioned earlier (src/main.py). Now tell me what functions are defined in it.",
        expected_files=["src/main.py"],
        expected_answer="functions listed",
    ),
    MemoryTask(
        task_id="history_2",
        category="history_reference",
        prompt="Recall the error we discussed earlier. Now find the line number in src/main.py that causes it.",
        expected_files=["src/main.py"],
        expected_answer="line number found",
    ),
    # 额外任务
    MemoryTask(
        task_id="fact_3",
        category="fact_lookup",
        prompt="What variables are defined in the global scope of config.py?",
        expected_files=["config.py"],
        expected_answer="variables listed",
    ),
    MemoryTask(
        task_id="fact_4",
        category="fact_lookup",
        prompt="What is the return type of the calculate function in math_utils.py?",
        expected_files=["math_utils.py"],
        expected_answer="float",
    ),
    MemoryTask(
        task_id="edit_3",
        category="edit_dependency",
        prompt="Read database.py and models.py. Add a new field to the User model and update the database schema accordingly.",
        expected_files=["database.py", "models.py"],
        expected_answer="both updated",
    ),
    MemoryTask(
        task_id="history_3",
        category="history_reference",
        prompt="Earlier we discussed the authentication flow. Now find the auth middleware in middleware.py.",
        expected_files=["middleware.py"],
        expected_answer="middleware found",
    ),
    MemoryTask(
        task_id="edit_4",
        category="edit_dependency",
        prompt="Read requirements.txt and setup.py. Update the version of a dependency in both files.",
        expected_files=["requirements.txt", "setup.py"],
        expected_answer="version updated",
    ),
    MemoryTask(
        task_id="history_4",
        category="history_reference",
        prompt="Remember the API endpoint we discussed. Now find its implementation in routes.py.",
        expected_files=["routes.py"],
        expected_answer="endpoint found",
    ),
]


class MemoryExperiment:
    """记忆实验

    使用方式:
        experiment = MemoryExperiment()
        results = experiment.run()
        report = experiment.generate_report(results)
    """

    def __init__(
        self,
        output_dir: str | Path | None = None,
        max_turns: int = 10,
    ) -> None:
        """初始化

        Args:
            output_dir: 输出目录
            max_turns: 每个任务最大轮次
        """
        if output_dir is None:
            output_dir = Path.cwd() / "docs" / "test-reports"
        self._output_dir = Path(output_dir)
        self._max_turns = max_turns

        # 定义配置
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
        """运行单个配置

        Args:
            config: 配置
            tasks: 任务列表

        Returns:
            实验结果
        """
        start_time = time.time()
        task_results = []
        total_repeated_reads = 0
        total_correct = 0
        total_memory_hits = 0
        total_tool_calls = 0

        for task in tasks:
            logger.info("  Running task: %s", task.task_id)
            result = self._run_single_task(config, task)
            task_results.append(result)

            total_repeated_reads += result.get("repeated_reads", 0)
            if result.get("correct", False):
                total_correct += 1
            total_memory_hits += result.get("memory_hits", 0)
            total_tool_calls += result.get("tool_calls", 0)

        duration = time.time() - start_time

        # 计算指标
        metrics = MemoryMetrics(
            repeated_reads=total_repeated_reads,
            correct_rate=total_correct / len(tasks) if tasks else 0.0,
            memory_hit_rate=total_memory_hits / total_tool_calls if total_tool_calls > 0 else 0.0,
            total_tool_calls=total_tool_calls,
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
        """运行单个任务

        Args:
            config: 配置
            task: 任务

        Returns:
            任务结果
        """
        # 模拟运行（实际需要集成 AgentLoop）
        # 这里返回模拟数据用于测试框架
        return {
            "task_id": task.task_id,
            "category": task.category,
            "correct": True,  # 模拟正确
            "repeated_reads": 0,
            "memory_hits": 1 if config.use_memory else 0,
            "tool_calls": 2,
            "duration": 0.5,
        }

    def generate_report(self, results: list[MemoryAblationResult]) -> str:
        """生成实验报告

        Args:
            results: 实验结果列表

        Returns:
            报告内容
        """
        report = []
        report.append("# Memory Experiment Report")
        report.append("")
        report.append("## 实验设计")
        report.append("")
        report.append("| 配置 | use_memory | use_irrelevant_memory |")
        report.append("|------|------------|----------------------|")
        for r in results:
            report.append(f"| {r.config.name} | {r.config.use_memory} | {r.config.use_irrelevant_memory} |")
        report.append("")

        report.append("## 测试场景")
        report.append("")
        report.append("| 类别 | 数量 |")
        report.append("|------|------|")
        categories = {}
        for task in MEMORY_TASKS:
            categories[task.category] = categories.get(task.category, 0) + 1
        for cat, count in categories.items():
            report.append(f"| {cat} | {count} |")
        report.append("")

        report.append("## 实验结果")
        report.append("")
        report.append("| 配置 | repeated_reads | correct_rate | memory_hit_rate | 总工具调用 | 耗时 |")
        report.append("|------|----------------|--------------|-----------------|-----------|------|")
        for r in results:
            m = r.metrics
            report.append(
                f"| {r.config.name} | {m.repeated_reads} | {m.correct_rate:.2%} | "
                f"{m.memory_hit_rate:.2%} | {m.total_tool_calls} | {r.duration:.2f}s |"
            )
        report.append("")

        report.append("## 结论")
        report.append("")
        for r in results:
            if r.config.use_memory and not r.config.use_irrelevant_memory:
                report.append(f"- **{r.config.name}**: 使用记忆系统，正确率 {r.metrics.correct_rate:.2%}")
            elif not r.config.use_memory:
                report.append(f"- **{r.config.name}**: 不使用记忆，正确率 {r.metrics.correct_rate:.2%}")
            else:
                report.append(f"- **{r.config.name}**: 使用无关记忆，正确率 {r.metrics.correct_rate:.2%}")
        report.append("")

        return "\n".join(report)

    def save_report(
        self,
        results: list[MemoryAblationResult],
        filename: str = "P2-memory-experiment.md",
    ) -> Path:
        """保存实验报告

        Args:
            results: 实验结果
            filename: 文件名

        Returns:
            保存路径
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        report_path = self._output_dir / filename

        report = self.generate_report(results)
        report_path.write_text(report, encoding="utf-8")

        logger.info("Report saved to: %s", report_path)
        return report_path


def run_memory_experiment() -> list[MemoryAblationResult]:
    """运行记忆实验的便捷函数

    Returns:
        实验结果列表
    """
    experiment = MemoryExperiment()
    results = experiment.run()
    experiment.save_report(results)
    return results
