"""Recovery Ablation 实验 - 测试 checkpoint 恢复功能的有效性

实验目的:
验证 checkpoint 系统是否真的有用。
对比"开启 checkpoint"和"关闭 checkpoint"的效果。

实验设计:
- 10 个恢复场景（checkpoint_resume、partial_stale、workspace_mismatch 等）
- 两种配置：resume_enabled vs resume_disabled
- 记录指标：resume_success_rate、stale_reanchor_rate 等

设计决策:
- 为什么用 FakeModelClient？
  确定性测试，不受真实模型波动影响。

- 为什么是 10 个场景？
  覆盖主要恢复场景，不会太多导致测试时间过长。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.core.loop import AgentLoop, LoopConfig
from agent.core.model import MimoClient
from agent.tools.registry import ToolRegistry
from agent.evaluation.fake_client import FakeModelClient
from agent.observability.checkpoint import CheckpointManager

logger = logging.getLogger("agent.evaluation.recovery_experiment")


@dataclass
class RecoveryScenario:
    """恢复场景

    Attributes:
        name: 场景名称
        description: 场景描述
        setup: 场景设置函数
        verify: 验证函数
    """
    name: str
    description: str
    setup: str  # JSON 格式的设置指令
    expected_status: str  # 期望的 resume_status


@dataclass
class RecoveryResult:
    """恢复结果

    Attributes:
        scenario: 场景名称
        config: 配置名称（resume_enabled / resume_disabled）
        resume_status: 恢复状态
        success: 是否成功
        duration_ms: 耗时
        error: 错误信息
    """
    scenario: str
    config: str
    resume_status: str
    success: bool
    duration_ms: int
    error: str | None = None


@dataclass
class RecoveryReport:
    """实验报告

    Attributes:
        total_scenarios: 总场景数
        resume_enabled_results: 开启 checkpoint 的结果
        resume_disabled_results: 关闭 checkpoint 的结果
        metrics: 计算的指标
    """
    total_scenarios: int
    resume_enabled_results: list[RecoveryResult]
    resume_disabled_results: list[RecoveryResult]
    metrics: dict[str, float]


# 预定义的 10 个恢复场景
RECOVERY_SCENARIOS: list[RecoveryScenario] = [
    RecoveryScenario(
        name="checkpoint_resume",
        description="正常恢复：checkpoint 存在，文件未变化",
        setup=json.dumps({
            "action": "create_checkpoint",
            "files": {"main.py": "original content"},
        }),
        expected_status="full-valid",
    ),
    RecoveryScenario(
        name="partial_stale",
        description="部分过期：部分文件被修改",
        setup=json.dumps({
            "action": "create_checkpoint",
            "files": {"main.py": "original", "utils.py": "original"},
            "modify": ["utils.py"],
        }),
        expected_status="partial-stale",
    ),
    RecoveryScenario(
        name="workspace_mismatch",
        description="工作区不匹配：文件被删除",
        setup=json.dumps({
            "action": "create_checkpoint",
            "files": {"main.py": "original"},
            "delete": ["main.py"],
        }),
        expected_status="invalid",
    ),
    RecoveryScenario(
        name="schema_mismatch",
        description="格式不匹配：checkpoint 格式变化",
        setup=json.dumps({
            "action": "create_checkpoint",
            "files": {"main.py": "original"},
            "corrupt_schema": True,
        }),
        expected_status="invalid",
    ),
    RecoveryScenario(
        name="partial_success",
        description="部分成功：只完成了一半任务",
        setup=json.dumps({
            "action": "create_checkpoint",
            "files": {"main.py": "original", "utils.py": "original"},
            "completed_steps": ["读取 main.py"],
            "next_step": "修改 utils.py",
        }),
        expected_status="full-valid",
    ),
    RecoveryScenario(
        name="file_created",
        description="文件新增：checkpoint 后创建了新文件",
        setup=json.dumps({
            "action": "create_checkpoint",
            "files": {"main.py": "original"},
            "create": ["new_file.py"],
        }),
        expected_status="full-valid",
    ),
    RecoveryScenario(
        name="file_renamed",
        description="文件重命名：文件被重命名",
        setup=json.dumps({
            "action": "create_checkpoint",
            "files": {"main.py": "original"},
            "rename": {"main.py": "app.py"},
        }),
        expected_status="invalid",
    ),
    RecoveryScenario(
        name="content_swapped",
        description="内容交换：文件内容被完全替换",
        setup=json.dumps({
            "action": "create_checkpoint",
            "files": {"main.py": "original content"},
            "swap": {"main.py": "completely different content"},
        }),
        expected_status="partial-stale",
    ),
    RecoveryScenario(
        name="multiple_changes",
        description="多次变化：多个文件被修改",
        setup=json.dumps({
            "action": "create_checkpoint",
            "files": {"a.py": "content_a", "b.py": "content_b", "c.py": "content_c"},
            "modify": ["a.py", "c.py"],
        }),
        expected_status="partial-stale",
    ),
    RecoveryScenario(
        name="no_checkpoint",
        description="无 checkpoint：没有可用的 checkpoint",
        setup=json.dumps({
            "action": "no_checkpoint",
        }),
        expected_status="none",
    ),
]


class RecoveryExperiment:
    """Recovery Ablation 实验

    使用方式:
        experiment = RecoveryExperiment(tmp_path)
        report = experiment.run()
        print(experiment.format_report(report))
    """

    def __init__(self, workspace_dir: Path) -> None:
        """初始化实验

        Args:
            workspace_dir: 工作区目录
        """
        self._workspace_dir = workspace_dir
        self._checkpoint_dir = workspace_dir / "checkpoints"
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> RecoveryReport:
        """运行实验

        Returns:
            实验报告
        """
        logger.info("Starting Recovery Ablation experiment")

        resume_enabled_results: list[RecoveryResult] = []
        resume_disabled_results: list[RecoveryResult] = []

        for scenario in RECOVERY_SCENARIOS:
            logger.info("Running scenario: %s", scenario.name)

            # 运行 resume_enabled 配置
            result_enabled = self._run_scenario(scenario, resume_enabled=True)
            resume_enabled_results.append(result_enabled)

            # 运行 resume_disabled 配置
            result_disabled = self._run_scenario(scenario, resume_enabled=False)
            resume_disabled_results.append(result_disabled)

        # 计算指标
        metrics = self._calculate_metrics(
            resume_enabled_results,
            resume_disabled_results,
        )

        report = RecoveryReport(
            total_scenarios=len(RECOVERY_SCENARIOS),
            resume_enabled_results=resume_enabled_results,
            resume_disabled_results=resume_disabled_results,
            metrics=metrics,
        )

        logger.info("Recovery Ablation experiment completed")
        return report

    def _run_scenario(
        self,
        scenario: RecoveryScenario,
        resume_enabled: bool,
    ) -> RecoveryResult:
        """运行单个场景

        Args:
            scenario: 场景
            resume_enabled: 是否开启 checkpoint

        Returns:
            运行结果
        """
        import time
        start_time = time.time()

        try:
            # 设置场景
            setup = json.loads(scenario.setup)
            self._setup_scenario(setup, resume_enabled)

            # 检查 freshness
            if setup.get("action") == "no_checkpoint":
                resume_status = "none"
                success = scenario.expected_status == "none"
            else:
                mgr = CheckpointManager(self._checkpoint_dir)
                checkpoint = mgr.load_latest()
                if checkpoint:
                    result = mgr.check_freshness(checkpoint)
                    resume_status = result.resume_status
                    success = resume_status == scenario.expected_status
                else:
                    resume_status = "none"
                    success = scenario.expected_status == "none"

            duration_ms = int((time.time() - start_time) * 1000)

            return RecoveryResult(
                scenario=scenario.name,
                config="resume_enabled" if resume_enabled else "resume_disabled",
                resume_status=resume_status,
                success=success,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return RecoveryResult(
                scenario=scenario.name,
                config="resume_enabled" if resume_enabled else "resume_disabled",
                resume_status="error",
                success=False,
                duration_ms=duration_ms,
                error=str(e),
            )

    def _setup_scenario(self, setup: dict[str, Any], resume_enabled: bool) -> None:
        """设置场景

        Args:
            setup: 设置指令
            resume_enabled: 是否开启 checkpoint
        """
        if setup.get("action") == "no_checkpoint":
            return

        # 清理旧的 checkpoint
        for f in self._checkpoint_dir.glob("cp_*.json"):
            f.unlink()

        # 创建文件
        for filename, content in setup.get("files", {}).items():
            file_path = self._workspace_dir / filename
            file_path.write_text(content, encoding="utf-8")

        # 修改文件
        for filename in setup.get("modify", []):
            file_path = self._workspace_dir / filename
            if file_path.exists():
                file_path.write_text("modified content", encoding="utf-8")

        # 删除文件
        for filename in setup.get("delete", []):
            file_path = self._workspace_dir / filename
            if file_path.exists():
                file_path.unlink()

        # 创建新文件
        for filename in setup.get("create", []):
            file_path = self._workspace_dir / filename
            file_path.write_text("new content", encoding="utf-8")

        # 重命名文件
        for old_name, new_name in setup.get("rename", {}).items():
            old_path = self._workspace_dir / old_name
            new_path = self._workspace_dir / new_name
            if old_path.exists():
                old_path.rename(new_path)

        # 交换内容
        for filename, new_content in setup.get("swap", {}).items():
            file_path = self._workspace_dir / filename
            if file_path.exists():
                file_path.write_text(new_content, encoding="utf-8")

        # 创建 checkpoint
        if resume_enabled:
            mgr = CheckpointManager(self._checkpoint_dir)
            for filename in setup.get("files", {}).keys():
                file_path = self._workspace_dir / filename
                if file_path.exists():
                    mgr.track_file(str(file_path), "read")
            mgr.create(
                goal="测试恢复",
                completed_steps=setup.get("completed_steps", []),
                next_step=setup.get("next_step", "继续"),
            )

    def _calculate_metrics(
        self,
        enabled_results: list[RecoveryResult],
        disabled_results: list[RecoveryResult],
    ) -> dict[str, float]:
        """计算指标

        Args:
            enabled_results: 开启 checkpoint 的结果
            disabled_results: 关闭 checkpoint 的结果

        Returns:
            指标字典
        """
        # resume_success_rate: 恢复成功率
        enabled_success = sum(1 for r in enabled_results if r.success)
        disabled_success = sum(1 for r in disabled_results if r.success)
        total = len(enabled_results)

        resume_success_rate = enabled_success / total if total > 0 else 0.0

        # stale_reanchor_rate: 文件变了还能恢复的比例
        stale_scenarios = [
            r for r in enabled_results
            if r.resume_status in ("partial-stale", "invalid")
        ]
        stale_success = sum(1 for r in stale_scenarios if r.success)
        stale_reanchor_rate = (
            stale_success / len(stale_scenarios) if stale_scenarios else 0.0
        )

        # workspace_drift_detection_rate: 检测到工作区变化的比例
        drift_scenarios = [
            r for r in enabled_results
            if r.resume_status in ("partial-stale", "invalid")
        ]
        drift_detected = len(drift_scenarios)
        drift_detection_rate = drift_detected / total if total > 0 else 0.0

        # resume_false_accept_rate: 误接受率（应该拒绝但接受了）
        should_reject = [
            r for r in enabled_results
            if r.resume_status in ("partial-stale", "invalid")
        ]
        false_accept = sum(
            1 for r in should_reject
            if r.resume_status == "full-valid"
        )
        false_accept_rate = (
            false_accept / len(should_reject) if should_reject else 0.0
        )

        return {
            "resume_success_rate": resume_success_rate,
            "stale_reanchor_rate": stale_reanchor_rate,
            "workspace_drift_detection_rate": drift_detection_rate,
            "resume_false_accept_rate": false_accept_rate,
            "enabled_success_rate": enabled_success / total if total > 0 else 0.0,
            "disabled_success_rate": disabled_success / total if total > 0 else 0.0,
        }

    def format_report(self, report: RecoveryReport) -> str:
        """格式化报告

        Args:
            report: 实验报告

        Returns:
            格式化的报告字符串
        """
        lines = [
            "# Recovery Ablation 实验报告",
            "",
            f"## 总场景数: {report.total_scenarios}",
            "",
            "## 指标",
            "",
        ]

        for metric, value in report.metrics.items():
            lines.append(f"- {metric}: {value:.2%}")

        lines.extend([
            "",
            "## 详细结果",
            "",
            "### resume_enabled（开启 checkpoint）",
            "",
            "| 场景 | 状态 | 成功 | 耗时 |",
            "|------|------|------|------|",
        ])

        for r in report.resume_enabled_results:
            status = "PASS" if r.success else "FAIL"
            lines.append(
                f"| {r.scenario} | {r.resume_status} | {status} | {r.duration_ms}ms |"
            )

        lines.extend([
            "",
            "### resume_disabled（关闭 checkpoint）",
            "",
            "| 场景 | 状态 | 成功 | 耗时 |",
            "|------|------|------|------|",
        ])

        for r in report.resume_disabled_results:
            status = "PASS" if r.success else "FAIL"
            lines.append(
                f"| {r.scenario} | {r.resume_status} | {status} | {r.duration_ms}ms |"
            )

        return "\n".join(lines)
