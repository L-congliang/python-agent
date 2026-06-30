"""文件摘要 - 避免重复读取文件

设计决策:
- 为什么只保留 180 字符？
  足够识别文件用途（类名、函数名、导入）
  不会占用太多 token
  Claude Code 也用类似长度

- 为什么需要 freshness 校验？
  文件可能被修改，摘要可能过期
  用 mtime + size 作为 freshness 指标，轻量级

- 为什么用 dict 存储？
  O(1) 查找
  file_path -> FileSummary 映射直观
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FileSummary:
    """文件摘要

    Attributes:
        path: 文件路径
        content: 摘要内容（最多 180 字符）
        freshness: 新鲜度指标（mtime + size）
        total_chars: 原始文件总字符数
    """
    path: str
    content: str
    freshness: str = ""  # "mtime:size" 格式
    total_chars: int = 0

    # 常量
    MAX_SUMMARY_LENGTH: int = 180


class FileSummaries:
    """文件摘要管理器

    使用方式:
        summaries = FileSummaries()
        summaries.update("src/main.py", content, file_mtime=123456, file_size=1000)
        summary = summaries.get("src/main.py")
    """

    def __init__(self, max_summaries: int = 50) -> None:
        """初始化

        Args:
            max_summaries: 最大摘要数量
        """
        self._summaries: dict[str, FileSummary] = {}
        self._max_summaries = max_summaries

    def update(
        self,
        file_path: str,
        content: str,
        file_mtime: float,
        file_size: int,
    ) -> FileSummary:
        """更新文件摘要

        Args:
            file_path: 文件路径
            content: 文件内容
            file_mtime: 文件修改时间
            file_size: 文件大小

        Returns:
            创建的 FileSummary
        """
        # 生成摘要（前 180 字符）
        summary_content = content[:FileSummary.MAX_SUMMARY_LENGTH]
        if len(content) > FileSummary.MAX_SUMMARY_LENGTH:
            summary_content += "..."

        # 生成 freshness 指标
        freshness = f"{file_mtime}:{file_size}"

        summary = FileSummary(
            path=file_path,
            content=summary_content,
            freshness=freshness,
            total_chars=len(content),
        )

        self._summaries[file_path] = summary

        # 淘汰多余的摘要
        if len(self._summaries) > self._max_summaries:
            self._evict_oldest()

        return summary

    def get(self, file_path: str) -> FileSummary | None:
        """获取文件摘要

        Args:
            file_path: 文件路径

        Returns:
            FileSummary 或 None
        """
        return self._summaries.get(file_path)

    def is_fresh(self, file_path: str) -> bool:
        """检查摘要是否新鲜（文件未修改）

        Args:
            file_path: 文件路径

        Returns:
            是否新鲜
        """
        summary = self._summaries.get(file_path)
        if not summary:
            return False

        try:
            stat = os.stat(file_path)
            current_freshness = f"{stat.st_mtime}:{stat.st_size}"
            return summary.freshness == current_freshness
        except OSError:
            return False

    def invalidate(self, file_path: str) -> None:
        """使摘要失效

        Args:
            file_path: 文件路径
        """
        if file_path in self._summaries:
            del self._summaries[file_path]

    def get_all(self) -> dict[str, FileSummary]:
        """获取所有摘要

        Returns:
            file_path -> FileSummary 映射
        """
        return dict(self._summaries)

    def clear(self) -> None:
        """清空所有摘要"""
        self._summaries.clear()

    def _evict_oldest(self) -> None:
        """淘汰最旧的摘要"""
        if self._summaries:
            oldest_key = next(iter(self._summaries))
            del self._summaries[oldest_key]
