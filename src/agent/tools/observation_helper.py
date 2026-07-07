"""Observation Helper - 工具输出截断与 Artifact 化统一

提供统一的截断逻辑，让 bash/read/grep/glob/edit 的长输出处理不再各自散落。

设计决策:
- 为什么需要统一？
  之前每个工具各自实现截断，格式不一致，且没有 artifact 化。
  统一后，所有工具的长输出都有相同的 preview + artifact 双层契约。

- 为什么保留尾部/头部策略不同？
  bash 保留尾部：命令输出的有用信息在最后（测试结果、错误信息）
  read/grep 保留头部：代码结构在开头（imports、类定义、函数签名）

- 为什么 preview 和 full 都保存？
  preview 回灌到消息历史（模型可见）
  full 保存到 artifact（用户可追溯）
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent.core.types import ObservationMetadata

logger = logging.getLogger("agent.tools.observation")

# 默认截断阈值
DEFAULT_MAX_LINES = 2000
DEFAULT_MAX_CHARS = 100_000  # 100KB

# 截断策略
TruncationStrategy = Literal["tail", "head"]
"""
tail: 保留尾部（bash 等命令输出）
head: 保留头部（文件读取、搜索结果）
"""


@dataclass
class TruncationResult:
    """截断结果

    Attributes:
        preview: 预览内容（截断后）
        was_truncated: 是否被截断
        full_lines: 完整内容的行数
        full_chars: 完整内容的字符数
    """
    preview: str
    was_truncated: bool
    full_lines: int
    full_chars: int


def truncate_output(
    output: str,
    max_lines: int = DEFAULT_MAX_LINES,
    max_chars: int = DEFAULT_MAX_CHARS,
    strategy: TruncationStrategy = "tail",
) -> TruncationResult:
    """统一截断逻辑

    Args:
        output: 原始输出
        max_lines: 最大行数
        max_chars: 最大字符数
        strategy: 截断策略（tail/head）

    Returns:
        TruncationResult: 截断结果
    """
    if not output:
        return TruncationResult(
            preview="",
            was_truncated=False,
            full_lines=0,
            full_chars=0,
        )

    lines = output.split('\n')
    full_lines = len(lines)
    full_chars = len(output)

    # 检查是否需要截断
    needs_truncation = full_lines > max_lines or full_chars > max_chars

    if not needs_truncation:
        return TruncationResult(
            preview=output,
            was_truncated=False,
            full_lines=full_lines,
            full_chars=full_chars,
        )

    # 执行截断
    if strategy == "tail":
        truncated = _truncate_tail(lines, max_lines)
        header = f"... (truncated {full_lines - max_lines} lines from head)\n"
    else:  # head
        truncated = _truncate_head(lines, max_lines)
        header = ""

    preview = header + '\n'.join(truncated)

    # 如果字符数仍然超过限制，进一步截断
    if len(preview) > max_chars:
        if strategy == "tail":
            preview = preview[-max_chars:]
        else:
            preview = preview[:max_chars]

    logger.debug(
        "Truncated output: %d lines -> %d lines, %d chars -> %d chars (strategy=%s)",
        full_lines, len(truncated), full_chars, len(preview), strategy,
    )

    return TruncationResult(
        preview=preview,
        was_truncated=True,
        full_lines=full_lines,
        full_chars=full_chars,
    )


def _truncate_tail(lines: list[str], max_lines: int) -> list[str]:
    """保留尾部"""
    return lines[-max_lines:]


def _truncate_head(lines: list[str], max_lines: int) -> list[str]:
    """保留头部"""
    return lines[:max_lines]


def build_observation(
    output: str,
    tool_name: str,
    artifact_dir: str | None = None,
    max_lines: int = DEFAULT_MAX_LINES,
    max_chars: int = DEFAULT_MAX_CHARS,
    strategy: TruncationStrategy = "tail",
) -> tuple[str, ObservationMetadata]:
    """构建 observation 双层契约

    这是工具层应该调用的主要接口。

    Args:
        output: 工具输出
        tool_name: 工具名称（用于 artifact 文件名）
        artifact_dir: artifact 保存目录（None 则不保存）
        max_lines: 最大行数
        max_chars: 最大字符数
        strategy: 截断策略

    Returns:
        (preview, observation_metadata) 元组
        preview: 模型可见的预览内容
        observation_metadata: 完整的 observation 元数据
    """
    result = truncate_output(output, max_lines, max_chars, strategy)

    artifact_path = None
    if result.was_truncated and artifact_dir:
        artifact_path = _save_artifact(output, tool_name, artifact_dir)

    observation = ObservationMetadata(
        preview=result.preview,
        artifact_path=artifact_path,
        was_truncated=result.was_truncated,
        full_output_chars=result.full_chars,
    )

    return result.preview, observation


def _save_artifact(output: str, tool_name: str, artifact_dir: str) -> str | None:
    """保存完整输出到 artifact 文件

    Args:
        output: 完整输出
        tool_name: 工具名称
        artifact_dir: artifact 保存目录

    Returns:
        artifact 文件路径，失败返回 None
    """
    try:
        os.makedirs(artifact_dir, exist_ok=True)

        # 生成唯一文件名
        import time
        timestamp = int(time.time() * 1000)
        filename = f"{tool_name}_{timestamp}.txt"
        filepath = os.path.join(artifact_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(output)

        logger.info("Saved artifact: %s (%d chars)", filepath, len(output))
        return filepath

    except Exception as e:
        logger.error("Failed to save artifact: %s", e)
        return None
