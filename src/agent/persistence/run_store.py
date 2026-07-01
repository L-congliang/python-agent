"""Run 工件存储 - 管理运行相关的文件

设计决策:
- 为什么用目录结构？
  每次运行一个目录，包含 trace、report、checkpoint。
  结构清晰，易于清理。

- 为什么自动生成 run_id？
  避免冲突，易于排序。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.persistence.run_store")


class RunStore:
    """Run 工件存储

    管理运行相关的文件（trace、report、checkpoint）。

    使用方式:
        store = RunStore(Path(".agent/runs"))
        run_dir = store.create_run_dir()
        # run_dir 下创建 trace.jsonl、report.json 等
    """

    def __init__(self, runs_dir: Path) -> None:
        """初始化 RunStore

        Args:
            runs_dir: 运行目录的父目录
        """
        self._runs_dir = runs_dir
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        logger.info("RunStore initialized: %s", runs_dir)

    def create_run_dir(self, run_id: str | None = None) -> Path:
        """创建运行目录

        Args:
            run_id: 运行 ID（可选，自动生成）

        Returns:
            运行目录路径
        """
        if run_id is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_id = f"run_{timestamp}"

        run_dir = self._runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Run directory created: %s", run_dir)
        return run_dir

    def get_run_dir(self, run_id: str) -> Path | None:
        """获取运行目录

        Args:
            run_id: 运行 ID

        Returns:
            运行目录路径，如果不存在则返回 None
        """
        run_dir = self._runs_dir / run_id
        if not run_dir.exists():
            logger.warning("Run directory not found: %s", run_id)
            return None
        return run_dir

    def list_runs(self) -> list[dict[str, Any]]:
        """列出所有运行

        Returns:
            运行摘要列表
        """
        runs = []
        for run_dir in sorted(
            self._runs_dir.iterdir(),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        ):
            if not run_dir.is_dir():
                continue

            run_info = {
                "run_id": run_dir.name,
                "created_at": datetime.fromtimestamp(
                    run_dir.stat().st_mtime
                ).isoformat(),
                "has_trace": (run_dir / "trace.jsonl").exists(),
                "has_report": (run_dir / "report.json").exists(),
                "has_checkpoint": any(run_dir.glob("checkpoint_*.json")),
            }
            runs.append(run_info)

        return runs

    def cleanup(self, keep_last: int = 10) -> int:
        """清理旧的运行目录

        Args:
            keep_last: 保留最近的运行数量

        Returns:
            清理的运行数量
        """
        runs = sorted(
            [d for d in self._runs_dir.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )

        if len(runs) <= keep_last:
            return 0

        to_delete = runs[keep_last:]
        for run_dir in to_delete:
            # 删除目录中的所有文件
            for file in run_dir.iterdir():
                file.unlink()
            run_dir.rmdir()
            logger.info("Deleted run directory: %s", run_dir.name)

        return len(to_delete)
