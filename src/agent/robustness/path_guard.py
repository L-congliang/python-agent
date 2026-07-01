"""
路径逃逸防护 - 验证文件路径不能跳出工作区

设计决策:
- 为什么用 resolve()？
  解析符号链接和 ..，获取真实路径
- 为什么在工具层检查？
  文件工具（read/write/edit）都需要检查，统一入口
"""

from __future__ import annotations

import os
from pathlib import Path


class PathGuard:
    """路径逃逸防护

    验证文件路径不能跳出工作区。
    路径解析后必须在 workspace root 内。
    """

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        """初始化

        Args:
            workspace_root: 工作区根目录。如果为 None，使用当前目录。
        """
        if workspace_root is None:
            self._root = Path.cwd().resolve()
        else:
            self._root = Path(workspace_root).resolve()

    @property
    def root(self) -> Path:
        """工作区根目录"""
        return self._root

    def check_path(self, file_path: str) -> tuple[bool, str]:
        """检查路径是否在工作区内

        Args:
            file_path: 文件路径（相对或绝对）

        Returns:
            (is_safe, message)
            - is_safe: 是否安全（在工作区内）
            - message: 错误信息（如果不安全）
        """
        try:
            # 解析路径
            target = Path(file_path)

            # 如果是相对路径，相对于工作区解析
            if not target.is_absolute():
                target = self._root / target

            # 解析真实路径（处理 .. 和符号链接）
            resolved = target.resolve()

            # 检查是否在工作区内
            try:
                resolved.relative_to(self._root)
                return True, ""
            except ValueError:
                return False, (
                    f"Path escape detected: '{file_path}' "
                    f"resolves to '{resolved}' which is outside workspace "
                    f"'{self._root}'"
                )

        except Exception as e:
            return False, f"Path validation error: {e}"

    def resolve_path(self, file_path: str) -> Path | None:
        """解析路径（如果安全）

        Args:
            file_path: 文件路径

        Returns:
            解析后的路径，如果不安全返回 None
        """
        is_safe, _ = self.check_path(file_path)
        if not is_safe:
            return None

        target = Path(file_path)
        if not target.is_absolute():
            target = self._root / target
        return target.resolve()
