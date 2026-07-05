"""文件摘要 - 避免重复读取文件

设计决策:
- 为什么升级为结构化摘要？
  前 180 字符截断丢失了太多结构信息
  结构化摘要能提取：文件职责、关键类/函数/常量、最近重点
  支持字段级匹配，而不只看路径和词重叠

- 为什么需要 freshness 校验？
  文件可能被修改，摘要可能过期
  用 mtime + size 作为 freshness 指标，轻量级
  写后主动 invalidate 或重建 summary

- 为什么用 dict 存储？
  O(1) 查找
  file_path -> FileSummary 映射直观
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FileSummary:
    """文件摘要（结构化版本）

    Attributes:
        path: 文件路径
        content: 摘要内容（兼容旧版本）
        responsibility: 文件职责（一行描述）
        key_entities: 关键类/函数/常量列表
        recent_focus: 最近一次读到的重点
        freshness: 新鲜度指标（mtime + size）
        total_chars: 原始文件总字符数
        is_pending_refresh: 是否待刷新（文件被修改后标记）
    """
    path: str
    content: str
    responsibility: str = ""
    key_entities: list[str] = field(default_factory=list)
    recent_focus: str = ""
    freshness: str = ""  # "mtime:size" 格式
    total_chars: int = 0
    is_pending_refresh: bool = False

    # 常量
    MAX_SUMMARY_LENGTH: int = 180
    MAX_ENTITIES: int = 10


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
        """更新文件摘要（结构化版本）

        Args:
            file_path: 文件路径
            content: 文件内容
            file_mtime: 文件修改时间
            file_size: 文件大小

        Returns:
            创建的 FileSummary
        """
        # 生成结构化摘要
        responsibility = self._extract_responsibility(content, file_path)
        key_entities = self._extract_key_entities(content)
        recent_focus = self._extract_recent_focus(content)

        # 生成兼容旧版本的 content（前 180 字符）
        summary_content = content[:FileSummary.MAX_SUMMARY_LENGTH]
        if len(content) > FileSummary.MAX_SUMMARY_LENGTH:
            summary_content += "..."

        # 生成 freshness 指标
        freshness = f"{file_mtime}:{file_size}"

        summary = FileSummary(
            path=file_path,
            content=summary_content,
            responsibility=responsibility,
            key_entities=key_entities,
            recent_focus=recent_focus,
            freshness=freshness,
            total_chars=len(content),
            is_pending_refresh=False,
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

    def mark_pending_refresh(self, file_path: str) -> None:
        """标记摘要待刷新

        Args:
            file_path: 文件路径
        """
        summary = self._summaries.get(file_path)
        if summary:
            summary.is_pending_refresh = True

    def get_all(self) -> dict[str, FileSummary]:
        """获取所有摘要

        Returns:
            file_path -> FileSummary 映射
        """
        return dict(self._summaries)

    def get_pending_refresh(self) -> list[str]:
        """获取所有待刷新的摘要路径

        Returns:
            待刷新的文件路径列表
        """
        return [path for path, summary in self._summaries.items() if summary.is_pending_refresh]

    def clear(self) -> None:
        """清空所有摘要"""
        self._summaries.clear()

    def _extract_responsibility(self, content: str, file_path: str) -> str:
        """提取文件职责

        Args:
            content: 文件内容
            file_path: 文件路径

        Returns:
            文件职责描述
        """
        # 从文件路径推断职责
        path_parts = file_path.replace("\\", "/").split("/")
        filename = path_parts[-1] if path_parts else ""

        # 从 docstring 或注释中提取职责
        lines = content.split("\n")
        for line in lines[:20]:  # 只看前 20 行
            line = line.strip()
            # 检查 docstring
            if line.startswith('"""') or line.startswith("'''"):
                # 提取第一行 docstring
                doc = line.replace('"""', "").replace("'''", "").strip()
                if doc:
                    return doc[:100]
            # 检查注释
            if line.startswith("#") and not line.startswith("#!"):
                comment = line[1:].strip()
                if comment and len(comment) > 10:
                    return comment[:100]

        # 从文件名推断
        if "test" in filename.lower():
            return f"测试文件: {filename}"
        if "config" in filename.lower():
            return f"配置文件: {filename}"
        if "model" in filename.lower():
            return f"模型定义: {filename}"
        if "utils" in filename.lower() or "helper" in filename.lower():
            return f"工具函数: {filename}"

        return f"源文件: {filename}"

    def _extract_key_entities(self, content: str) -> list[str]:
        """提取关键类/函数/常量

        Args:
            content: 文件内容

        Returns:
            关键实体列表
        """
        entities = []

        # 提取类名
        class_pattern = r'^class\s+(\w+)'
        for match in re.finditer(class_pattern, content, re.MULTILINE):
            entities.append(f"class:{match.group(1)}")

        # 提取函数名（顶层函数）
        func_pattern = r'^def\s+(\w+)'
        for match in re.finditer(func_pattern, content, re.MULTILINE):
            entities.append(f"func:{match.group(1)}")

        # 提取常量（全大写变量）
        const_pattern = r'^([A-Z_][A-Z0-9_]*)\s*='
        for match in re.finditer(const_pattern, content, re.MULTILINE):
            entities.append(f"const:{match.group(1)}")

        # 限制数量
        return entities[:FileSummary.MAX_ENTITIES]

    def _extract_recent_focus(self, content: str) -> str:
        """提取最近重点

        Args:
            content: 文件内容

        Returns:
            最近重点描述
        """
        # 提取最后几行的注释或 docstring
        lines = content.split("\n")
        focus_lines = []

        # 从后往前找注释
        for line in reversed(lines[-20:]):
            line = line.strip()
            if line.startswith("#") or line.startswith('"""') or line.startswith("'''"):
                focus_lines.insert(0, line)
                if len(focus_lines) >= 3:
                    break
            elif focus_lines:
                break

        if focus_lines:
            return " ".join(focus_lines)[:100]

        # 如果没有注释，返回最后修改的函数/类
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("def ") or line.startswith("class "):
                return line[:100]

        return ""

    def _evict_oldest(self) -> None:
        """淘汰最旧的摘要"""
        if self._summaries:
            oldest_key = next(iter(self._summaries))
            del self._summaries[oldest_key]
