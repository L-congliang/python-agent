"""Workspace 快照 - 启动时捕获工作区状态

设计决策:
- 为什么只记录最近 5 个提交？
  足够了解最近改动，不会占用太多空间。

- 为什么只读 README 和 pyproject.toml？
  这两个文件最能代表项目信息。
  读太多文件会增加启动时间。
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.observability.workspace")


class WorkspaceSnapshot:
    """Workspace 快照

    在启动时捕获工作区状态：git 分支、最近提交、项目文档。

    使用方式:
        snapshot = WorkspaceSnapshot(Path("."))
        info = snapshot.capture()
        # info 包含 git_branch, recent_commits, project_docs
    """

    # 最近提交数量
    MAX_COMMITS = 5

    # 项目文档最大行数
    MAX_DOC_LINES = 200

    def __init__(self, workspace_root: Path) -> None:
        """初始化 WorkspaceSnapshot

        Args:
            workspace_root: 工作区根目录
        """
        self._workspace_root = workspace_root

    def capture(self) -> dict[str, Any]:
        """捕获工作区状态

        Returns:
            工作区信息字典
        """
        info: dict[str, Any] = {
            "workspace_root": str(self._workspace_root),
            "git_branch": None,
            "recent_commits": [],
            "project_docs": {},
        }

        # 捕获 git 信息
        git_info = self._capture_git()
        info.update(git_info)

        # 捕获项目文档
        docs = self._capture_docs()
        info["project_docs"] = docs

        logger.info("Workspace snapshot captured")
        return info

    def _capture_git(self) -> dict[str, Any]:
        """捕获 git 信息

        Returns:
            git 信息字典
        """
        result: dict[str, Any] = {
            "git_branch": None,
            "recent_commits": [],
        }

        try:
            # 获取当前分支
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self._workspace_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if branch.returncode == 0:
                result["git_branch"] = branch.stdout.strip()

            # 获取最近提交
            log = subprocess.run(
                ["git", "log", f"--max-count={self.MAX_COMMITS}", "--oneline"],
                cwd=self._workspace_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if log.returncode == 0:
                result["recent_commits"] = [
                    line.strip()
                    for line in log.stdout.strip().split("\n")
                    if line.strip()
                ]

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("Failed to capture git info: %s", e)

        return result

    def _capture_docs(self) -> dict[str, str]:
        """捕获项目文档

        Returns:
            文档内容字典
        """
        docs: dict[str, str] = {}

        # 要读取的文档
        doc_files = ["README.md", "pyproject.toml"]

        for doc_name in doc_files:
            doc_path = self._workspace_root / doc_name
            if not doc_path.exists():
                continue

            try:
                with open(doc_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                # 截断到最大行数
                if len(lines) > self.MAX_DOC_LINES:
                    lines = lines[: self.MAX_DOC_LINES]
                    lines.append(f"\n... (truncated, {len(lines)} lines total)")

                docs[doc_name] = "".join(lines)

            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Failed to read %s: %s", doc_name, e)

        return docs
