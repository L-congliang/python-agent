"""Prompt Ablation Experiment - 对比不同 prompt 版本的工具选择准确率

测试配置:
1. baseline: 最简 prompt（只写工具列表）
2. +identity: 加 Identity 部分
3. +tool_guide: 加 Tool Selection Guide
4. +full: 完整优化 prompt（Identity + Behavior + Tool Guide）

记录:
- first_try_accuracy: 第一次就选对工具的比例
- tool_accuracy: 最终选对工具的比例
- avg_prompt_tokens: 平均 prompt token 数
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger("agent.experiments.prompt_ablation")


def _load_env() -> None:
    """加载 .env 文件"""
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).parent.parent.parent.parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            logger.info("Loaded .env from: %s", env_path)
            return
    logger.warning("No .env file found")


_load_env()


@dataclass
class AblationTask:
    """单个测试任务"""

    id: str
    prompt: str
    expected_tool: str  # 期望的工具名
    description: str = ""


@dataclass
class TaskResult:
    """单个任务的执行结果"""

    task_id: str
    expected_tool: str
    actual_tool: str
    is_correct: bool
    prompt_tokens: int = 0
    error: str = ""


@dataclass
class ConfigResult:
    """单个配置的汇总结果"""

    config_name: str
    first_try_accuracy: float
    tool_accuracy: float
    avg_prompt_tokens: float
    task_results: list[TaskResult] = field(default_factory=list)


# 标准测试任务集
STANDARD_TASKS: list[AblationTask] = [
    # file_read 任务
    AblationTask("read_1", "读取 src/main.py 的内容", "read", "读取文件"),
    AblationTask("read_2", "看看 config.json 里有什么", "read", "查看配置"),
    AblationTask("read_3", "显示 tests/test_main.py 的前 50 行", "read", "读取文件行范围"),
    AblationTask("read_4", "打开 README.md 看看", "read", "打开文件"),
    # file_edit 任务
    AblationTask("edit_1", "把 src/main.py 第 10 行的 foo 改成 bar", "edit", "修改文件"),
    AblationTask("edit_2", "在 src/utils.py 里把 import os 改成 import os.path", "edit", "修改导入"),
    AblationTask("edit_3", "修改 src/config.py 中的 DEBUG = False 为 DEBUG = True", "edit", "修改配置"),
    AblationTask("edit_4", "把 requirements.txt 里的 requests==2.28 改成 requests==2.31", "edit", "修改依赖版本"),
    # file_write 任务
    AblationTask("write_1", "创建一个新文件 test.py，内容是 print('hello')", "write", "创建新文件"),
    AblationTask("write_2", "新建一个 .gitignore 文件", "write", "创建配置文件"),
    AblationTask("write_3", "创建 src/utils/__init__.py", "write", "创建包文件"),
    # grep 任务
    AblationTask("grep_1", "搜索所有包含 TODO 的文件", "grep", "搜索代码"),
    AblationTask("grep_2", "找到所有 import os 的地方", "grep", "搜索导入"),
    AblationTask("grep_3", "搜索所有 .py 文件中的 class 定义", "grep", "搜索类定义"),
    AblationTask("grep_4", "找一下哪里用了 requests.get", "grep", "搜索函数调用"),
    # glob 任务
    AblationTask("glob_1", "找到所有 .py 文件", "glob", "查找 Python 文件"),
    AblationTask("glob_2", "列出 src/ 下的所有目录", "glob", "列出目录"),
    AblationTask("glob_3", "找到所有测试文件", "glob", "查找测试文件"),
    # bash 任务
    AblationTask("bash_1", "运行 pytest 测试", "bash", "运行测试"),
    AblationTask("bash_2", "查看 git status", "bash", "Git 操作"),
    AblationTask("bash_3", "安装依赖 pip install requests", "bash", "安装依赖"),
    AblationTask("bash_4", "运行 python main.py", "bash", "运行脚本"),
]


class PromptAblationExperiment:
    """Prompt Ablation 实验

    使用方式:
        experiment = PromptAblationExperiment()
        results = experiment.run()
        report = experiment.generate_report(results)
    """

    def __init__(
        self,
        tasks: list[AblationTask] | None = None,
        output_dir: str | Path = "docs/test-reports",
    ) -> None:
        """初始化实验

        Args:
            tasks: 测试任务集（默认使用 STANDARD_TASKS）
            output_dir: 报告输出目录
        """
        self._tasks = tasks or STANDARD_TASKS
        self._output_dir = Path(output_dir)

    def run(self) -> list[ConfigResult]:
        """运行实验，对比 4 个配置

        Returns:
            4 个配置的结果列表
        """
        from agent.core.model import MimoClient, ModelConfig
        from agent.prompts.builder import SystemPromptBuilder
        from agent.tools.registry import ToolRegistry
        from agent.tools.bash import bash_tool
        from agent.tools.file_read import file_read_tool
        from agent.tools.file_write import file_write_tool
        from agent.tools.file_edit import file_edit_tool
        from agent.tools.grep import grep_tool
        from agent.tools.glob import glob_tool

        # 从环境变量获取 API 配置
        api_key = os.environ.get("MIMO_API_KEY", "")
        base_url = os.environ.get(
            "MIMO_BASE_URL",
            "https://token-plan-cn.xiaomimimo.com/anthropic",
        )
        model_name = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")

        if not api_key:
            raise ValueError("MIMO_API_KEY not set. Export it or pass via environment.")

        # 创建模型客户端
        config = ModelConfig(api_key=api_key, base_url=base_url, model=model_name)
        client = MimoClient(config)

        # 创建工具注册表
        registry = ToolRegistry()
        for tool in [bash_tool, file_read_tool, file_write_tool, file_edit_tool, grep_tool, glob_tool]:
            registry.register(tool)

        # 4 个配置
        configs = [
            ("baseline", self._build_baseline_prompt(registry)),
            ("+identity", self._build_identity_prompt(registry)),
            ("+tool_guide", self._build_tool_guide_prompt(registry)),
            ("+full", self._build_full_prompt(registry)),
        ]

        results: list[ConfigResult] = []
        for config_name, system_prompt in configs:
            logger.info("Running config: %s", config_name)
            result = self._run_config(config_name, system_prompt, client)
            results.append(result)

        return results

    def _run_config(
        self,
        config_name: str,
        system_prompt: str,
        client: Any,
    ) -> ConfigResult:
        """运行单个配置

        Args:
            config_name: 配置名称
            system_prompt: 系统提示词
            client: 模型客户端

        Returns:
            配置结果
        """
        task_results: list[TaskResult] = []
        correct_count = 0
        total_tokens = 0

        for task in self._tasks:
            try:
                result = self._run_single_task(task, system_prompt, client)
                task_results.append(result)
                if result.is_correct:
                    correct_count += 1
                total_tokens += result.prompt_tokens
            except Exception as e:
                logger.error("Task %s failed: %s", task.id, e)
                task_results.append(TaskResult(
                    task_id=task.id,
                    expected_tool=task.expected_tool,
                    actual_tool="",
                    is_correct=False,
                    error=str(e),
                ))

        total = len(self._tasks)
        accuracy = correct_count / total if total > 0 else 0.0
        avg_tokens = total_tokens / total if total > 0 else 0.0

        return ConfigResult(
            config_name=config_name,
            first_try_accuracy=accuracy,
            tool_accuracy=accuracy,
            avg_prompt_tokens=avg_tokens,
            task_results=task_results,
        )

    def _run_single_task(
        self,
        task: AblationTask,
        system_prompt: str,
        client: Any,
    ) -> TaskResult:
        """运行单个任务

        Args:
            task: 测试任务
            system_prompt: 系统提示词
            client: 模型客户端

        Returns:
            任务结果
        """
        from agent.core.adapters.mimo_adapter import MimoAdapter

        adapter = MimoAdapter()

        # 调用模型
        messages = [{"role": "user", "content": task.prompt}]
        stream_result = client.chat_stream(messages, system=system_prompt)

        # 消费所有 chunk
        list(stream_result.text)
        content_blocks = stream_result.content_blocks

        # 用 MimoAdapter 解析工具调用（mimo 用 XML 格式，不是原生 tool_use）
        parsed = adapter.parse_response(content_blocks)
        actual_tool = ""
        if parsed.tool_calls:
            actual_tool = parsed.tool_calls[0].name

        # 计算 prompt tokens
        prompt_tokens = len(system_prompt) // 4  # 粗略估算
        if stream_result.usage:
            prompt_tokens = stream_result.usage.get("input_tokens", prompt_tokens)

        is_correct = actual_tool == task.expected_tool

        return TaskResult(
            task_id=task.id,
            expected_tool=task.expected_tool,
            actual_tool=actual_tool,
            is_correct=is_correct,
            prompt_tokens=prompt_tokens,
        )

    def _build_baseline_prompt(self, registry: Any) -> str:
        """构建 baseline prompt（只写工具列表）"""
        tools = registry.get_enabled_tools()
        parts = ["你是一个编程助手。"]
        tool_desc = "可用工具:\n"
        for tool in tools:
            tool_desc += f"- {tool.name}: {tool.description}\n"
        parts.append(tool_desc)
        return "\n\n".join(parts)

    def _build_identity_prompt(self, registry: Any) -> str:
        """构建 +identity prompt"""
        from agent.prompts.builder import SystemPromptBuilder
        tools = registry.get_enabled_tools()
        parts = [SystemPromptBuilder.build_identity()]
        tool_desc = "可用工具:\n"
        for tool in tools:
            tool_desc += f"- {tool.name}: {tool.description}\n"
        parts.append(tool_desc)
        return "\n\n".join(parts)

    def _build_tool_guide_prompt(self, registry: Any) -> str:
        """构建 +tool_guide prompt"""
        from agent.prompts.builder import SystemPromptBuilder
        tools = registry.get_enabled_tools()
        parts = ["你是一个编程助手。"]
        parts.append(SystemPromptBuilder.build_tool_selection_guide())
        tool_desc = "可用工具:\n"
        for tool in tools:
            tool_desc += f"- {tool.name}: {tool.description}\n"
        parts.append(tool_desc)
        return "\n\n".join(parts)

    def _build_full_prompt(self, registry: Any) -> str:
        """构建 +full prompt"""
        from agent.prompts.builder import SystemPromptBuilder
        tools = registry.get_enabled_tools()
        parts = [
            SystemPromptBuilder.build_identity(),
            SystemPromptBuilder.build_behavior_guidelines(),
            SystemPromptBuilder.build_tool_selection_guide(),
        ]
        tool_desc = "可用工具:\n"
        for tool in tools:
            tool_desc += f"- {tool.name}: {tool.description}\n"
        parts.append(tool_desc)
        return "\n\n".join(parts)

    def generate_report(self, results: list[ConfigResult]) -> str:
        """生成实验报告

        Args:
            results: 4 个配置的结果

        Returns:
            Markdown 格式的报告
        """
        lines = [
            "# P6 Prompt Ablation Experiment",
            "",
            "## 实验目的",
            "",
            "对比不同 prompt 版本的工具选择准确率，验证 System Prompt 优化效果。",
            "",
            "## 实验配置",
            "",
            "| 配置 | 说明 |",
            "|------|------|",
            "| baseline | 最简 prompt（只写工具列表） |",
            "| +identity | 加 Identity 部分 |",
            "| +tool_guide | 加 Tool Selection Guide |",
            "| +full | 完整优化 prompt |",
            "",
            "## 测试任务集",
            "",
            f"共 {len(self._tasks)} 个任务，覆盖所有工具类型。",
            "",
            "## 结果",
            "",
            "| 配置 | tool_accuracy | avg_prompt_tokens |",
            "|------|---------------|-------------------|",
        ]

        for r in results:
            lines.append(
                f"| {r.config_name} | {r.tool_accuracy:.1%} | {r.avg_prompt_tokens:.0f} |"
            )

        lines.extend([
            "",
            "## 结论",
            "",
        ])

        # 找最佳配置
        best = max(results, key=lambda r: r.tool_accuracy)
        lines.append(f"最优配置: **{best.config_name}** (tool_accuracy={best.tool_accuracy:.1%})")

        # 计算提升
        if results:
            baseline = results[0]
            if baseline.tool_accuracy > 0:
                improvement = (best.tool_accuracy - baseline.tool_accuracy) / baseline.tool_accuracy
                lines.append(f"相比 baseline 提升: **{improvement:.1%}**")

        return "\n".join(lines)

    def save_report(self, results: list[ConfigResult]) -> Path:
        """保存报告到文件

        Args:
            results: 实验结果

        Returns:
            报告文件路径
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        report_path = self._output_dir / "P6-prompt-ablation.md"
        report = self.generate_report(results)
        report_path.write_text(report, encoding="utf-8")
        logger.info("Report saved to: %s", report_path)
        return report_path
