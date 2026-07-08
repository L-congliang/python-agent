"""Checkpoint 系统 - 断点续传 + freshness 检测

设计决策:
- 为什么用 hash + mtime 双重检测？
  mtime 快但不准确（touch 会误报），hash 慢但精确。
  策略: mtime 先筛，hash 再验，大文件只用 mtime。

- 为什么只追踪 agent 操作过的文件？
  减少检测开销，只关注相关文件。

- 为什么 checkpoint 是只读的？
  checkpoint 一旦创建就不应该修改，保证一致性。
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.observability.checkpoint")


@dataclass
class TrackedFile:
    """被追踪的文件信息

    Attributes:
        path: 文件路径
        hash: 文件内容 hash
        mtime: 修改时间戳
        size: 文件大小
        last_operation: 最后操作类型（read/write/edit）
    """
    path: str
    hash: str
    mtime: float
    size: int
    last_operation: str


@dataclass
class Checkpoint:
    """Checkpoint 快照

    Attributes:
        checkpoint_id: 检查点 ID
        run_id: 运行 ID
        created_at: 创建时间
        goal: 当前目标
        completed_steps: 已完成步骤
        next_step: 下一步计划
        tracked_files: 被追踪的文件
        messages_snapshot: 消息历史快照（可选）
    """
    checkpoint_id: str
    run_id: str
    created_at: str
    goal: str
    completed_steps: list[str]
    next_step: str
    tracked_files: dict[str, TrackedFile]
    messages_snapshot: list[dict[str, Any]] | None = None


@dataclass
class FreshnessResult:
    """Freshness 检测结果

    Attributes:
        resume_status: 恢复状态（full-valid / partial-stale / invalid）
        file_statuses: 各文件状态
        message: 状态说明
    """
    resume_status: str  # "full-valid" | "partial-stale" | "invalid"
    file_statuses: dict[str, str]  # file_path -> status
    message: str


class CheckpointManager:
    """Checkpoint 管理器

    管理 checkpoint 的创建、保存、加载和 freshness 检测。

    使用方式:
        mgr = CheckpointManager(Path(".agent/checkpoints"))
        mgr.track_file("main.py", "read")
        checkpoint = mgr.create(
            goal="重构 main.py",
            completed_steps=["读取 main.py"],
            next_step="执行替换",
        )
        # 恢复时
        checkpoint = mgr.load_latest()
        if checkpoint:
            result = mgr.check_freshness(checkpoint)
            if result.resume_status == "full-valid":
                # 可以继续
    """

    # 大文件阈值（1MB），超过此大小只用 mtime 检测
    LARGE_FILE_THRESHOLD = 1024 * 1024

    def __init__(self, checkpoint_dir: Path) -> None:
        """初始化 CheckpointManager

        Args:
            checkpoint_dir: checkpoint 存储目录
        """
        self._checkpoint_dir = checkpoint_dir
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # 当前追踪的文件
        self._tracked_files: dict[str, TrackedFile] = {}
        logger.info("CheckpointManager initialized: %s", checkpoint_dir)

    def track_file(self, file_path: str, operation: str) -> None:
        """追踪一个文件

        Args:
            file_path: 文件路径（绝对或相对）
            operation: 操作类型（read/write/edit）
        """
        path = Path(file_path)
        if not path.exists():
            logger.debug("Cannot track non-existent file: %s", file_path)
            return

        stat = path.stat()
        file_hash = self._compute_hash(path)

        self._tracked_files[str(path)] = TrackedFile(
            path=str(path),
            hash=file_hash,
            mtime=stat.st_mtime,
            size=stat.st_size,
            last_operation=operation,
        )
        logger.debug("Tracking file: %s (%s)", file_path, operation)

    def create(
        self,
        goal: str,
        completed_steps: list[str],
        next_step: str,
        run_id: str | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> Checkpoint:
        """创建 checkpoint

        Args:
            goal: 当前目标
            completed_steps: 已完成步骤
            next_step: 下一步计划
            run_id: 运行 ID（可选）
            messages: 消息历史快照（可选）

        Returns:
            创建的 checkpoint
        """
        checkpoint_id = f"cp_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        created_at = datetime.now(timezone.utc).isoformat()

        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            run_id=run_id or "unknown",
            created_at=created_at,
            goal=goal,
            completed_steps=completed_steps,
            next_step=next_step,
            tracked_files=self._tracked_files.copy(),
            messages_snapshot=messages,
        )

        # 保存到文件
        self._save_checkpoint(checkpoint)
        logger.info("Checkpoint created: %s", checkpoint_id)
        return checkpoint

    def load_latest(self) -> Checkpoint | None:
        """加载最新的 checkpoint

        Returns:
            最新的 checkpoint，如果没有则返回 None
        """
        checkpoint_files = sorted(
            self._checkpoint_dir.glob("cp_*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        if not checkpoint_files:
            logger.info("No checkpoint found")
            return None

        return self._load_checkpoint(checkpoint_files[0])

    def load(self, checkpoint_id: str) -> Checkpoint | None:
        """加载指定的 checkpoint

        Args:
            checkpoint_id: checkpoint ID

        Returns:
            checkpoint，如果不存在则返回 None
        """
        checkpoint_file = self._checkpoint_dir / f"{checkpoint_id}.json"
        if not checkpoint_file.exists():
            logger.warning("Checkpoint not found: %s", checkpoint_id)
            return None

        return self._load_checkpoint(checkpoint_file)

    def check_freshness(self, checkpoint: Checkpoint) -> FreshnessResult:
        """检测 checkpoint 的 freshness

        检查 checkpoint 中追踪的文件是否被修改。

        Args:
            checkpoint: 要检测的 checkpoint

        Returns:
            freshness 检测结果
        """
        file_statuses: dict[str, str] = {}
        has_invalid = False
        has_stale = False

        for file_path, tracked in checkpoint.tracked_files.items():
            path = Path(file_path)

            # 文件不存在
            if not path.exists():
                file_statuses[file_path] = "deleted"
                has_invalid = True
                continue

            stat = path.stat()

            # 文件大小变化
            if stat.st_size != tracked.size:
                file_statuses[file_path] = "modified"
                has_stale = True
                continue

            # mtime 没变，跳过 hash 检测
            if stat.st_mtime == tracked.mtime:
                file_statuses[file_path] = "unchanged"
                continue

            # 大文件只用 mtime
            if stat.st_size > self.LARGE_FILE_THRESHOLD:
                file_statuses[file_path] = "maybe_modified"
                has_stale = True
                continue

            # 计算 hash 验证
            current_hash = self._compute_hash(path)
            if current_hash == tracked.hash:
                file_statuses[file_path] = "unchanged"  # touch 但没改内容
            else:
                file_statuses[file_path] = "modified"
                has_stale = True

        # 决定 resume_status
        if has_invalid:
            resume_status = "invalid"
            message = "核心文件被删除或修改，建议重新开始"
        elif has_stale:
            resume_status = "partial-stale"
            message = "部分文件被修改，可以继续但需谨慎"
        else:
            resume_status = "full-valid"
            message = "所有文件未变化，可以安全继续"

        result = FreshnessResult(
            resume_status=resume_status,
            file_statuses=file_statuses,
            message=message,
        )

        logger.info(
            "Freshness check: status=%s, files=%d",
            resume_status,
            len(file_statuses),
        )
        return result

    def _compute_hash(self, path: Path) -> str:
        """计算文件 hash

        Args:
            path: 文件路径

        Returns:
            文件内容的 MD5 hash
        """
        hasher = hashlib.md5()
        with open(path, "rb") as f:
            # 分块读取，避免大文件占用太多内存
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """保存 checkpoint 到文件

        Args:
            checkpoint: 要保存的 checkpoint
        """
        data = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "run_id": checkpoint.run_id,
            "created_at": checkpoint.created_at,
            "goal": checkpoint.goal,
            "completed_steps": checkpoint.completed_steps,
            "next_step": checkpoint.next_step,
            "tracked_files": {
                path: {
                    "path": tracked.path,
                    "hash": tracked.hash,
                    "mtime": tracked.mtime,
                    "size": tracked.size,
                    "last_operation": tracked.last_operation,
                }
                for path, tracked in checkpoint.tracked_files.items()
            },
            "messages_snapshot": checkpoint.messages_snapshot,
        }

        file_path = self._checkpoint_dir / f"{checkpoint.checkpoint_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_checkpoint(self, file_path: Path) -> Checkpoint:
        """从文件加载 checkpoint

        Args:
            file_path: checkpoint 文件路径

        Returns:
            加载的 checkpoint
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tracked_files = {}
        for path, tracked_data in data.get("tracked_files", {}).items():
            tracked_files[path] = TrackedFile(
                path=tracked_data["path"],
                hash=tracked_data["hash"],
                mtime=tracked_data["mtime"],
                size=tracked_data["size"],
                last_operation=tracked_data["last_operation"],
            )

        return Checkpoint(
            checkpoint_id=data["checkpoint_id"],
            run_id=data["run_id"],
            created_at=data["created_at"],
            goal=data["goal"],
            completed_steps=data["completed_steps"],
            next_step=data["next_step"],
            tracked_files=tracked_files,
            messages_snapshot=data.get("messages_snapshot"),
        )
