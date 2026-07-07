"""Session Policy - 内存态权限策略

在当前 session 内缓存用户的权限决策，减少重复 ASK。

设计决策:
- 为什么只做内存态？
  权限策略是敏感数据，持久化会增加安全风险。
  session 结束后策略自动清空，符合最小权限原则。

- 为什么按精确 command / 规范化路径匹配？
  最小化实现：先支持精确匹配，再逐步扩展。
  避免通配符带来的安全边界模糊问题。

- 为什么 DENY 不能被 session allow 绕过？
  DENY 是系统级策略（如 plan mode），必须始终优先。
  session allow 只能绕过 ASK，不能绕过 DENY。

- 为什么 allow-once 不写入 session store？
  allow-once 只对当前这一次操作有效，不应该影响后续操作。
  如果误写入，会把一次授权变成整轮授权。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal


# ============================================================
# 数据结构
# ============================================================


@dataclass
class PermissionScope:
    """权限作用域

    Attributes:
        scope: once（本次）或 session（本 session）
    """
    scope: Literal["once", "session"]


@dataclass
class SessionPermissionRecord:
    """Session 权限记录

    Attributes:
        tool_name: 工具名称
        key: 匹配 key（bash: 精确 command，write/edit: 规范化路径）
        scope: 作用域
    """
    tool_name: str
    key: str
    scope: Literal["once", "session"]


# ============================================================
# Session Policy Store
# ============================================================


class SessionPermissionPolicy:
    """Session 级权限策略

    职责:
    - 记录用户的 allow-once / allow-session 决策
    - 查询是否命中 session allow
    - 清空 session policy

    使用方式:
        policy = SessionPermissionPolicy()
        policy.remember_allow("bash", "ls -la", scope="session")
        policy.is_allowed("bash", "ls -la")  # True
        policy.is_allowed("bash", "rm -rf /")  # False
        policy.clear()
    """

    def __init__(self) -> None:
        """初始化 session policy"""
        # session allow 存储：{(tool_name, key): scope}
        self._allowed: dict[tuple[str, str], Literal["session"]] = {}

    def is_allowed(self, tool_name: str, key: str) -> bool:
        """检查是否命中 session allow

        Args:
            tool_name: 工具名称
            key: 匹配 key

        Returns:
            True 如果命中 session allow
        """
        return (tool_name, key) in self._allowed

    def remember_allow(
        self,
        tool_name: str,
        key: str,
        scope: Literal["once", "session"],
    ) -> None:
        """记录 allow 决策

        Args:
            tool_name: 工具名称
            key: 匹配 key
            scope: 作用域（once 或 session）

        注意：
        - allow-once 不写入 session store，只对当前操作有效
        - allow-session 写入 session store，对后续相同操作有效
        """
        if scope == "session":
            self._allowed[(tool_name, key)] = "session"
        # allow-once 不写入，只返回 True 让调用方知道是 allow-once

    def clear(self) -> None:
        """清空 session policy"""
        self._allowed.clear()

    def get_allowed_count(self) -> int:
        """获取当前 session allow 的数量

        Returns:
            session allow 的数量
        """
        return len(self._allowed)


# ============================================================
# 辅助函数
# ============================================================


def normalize_bash_command(command: str) -> str:
    """规范化 bash 命令

    去除首尾空白，但保留命令内部的空格。

    Args:
        command: 原始命令

    Returns:
        规范化后的命令
    """
    return command.strip()


def normalize_file_path(file_path: str, cwd: str = ".") -> str:
    """规范化文件路径

    转换为绝对路径，处理相对路径。

    Args:
        file_path: 原始路径
        cwd: 当前工作目录

    Returns:
        规范化后的绝对路径
    """
    if os.path.isabs(file_path):
        return os.path.normpath(file_path)
    return os.path.normpath(os.path.abspath(os.path.join(cwd, file_path)))


def extract_permission_key(
    tool_name: str,
    tool_input: dict,
    cwd: str = ".",
) -> str | None:
    """从工具输入中提取权限匹配 key

    Args:
        tool_name: 工具名称
        tool_input: 工具输入
        cwd: 当前工作目录

    Returns:
        匹配 key，或 None（不支持的工具）
    """
    if tool_name == "bash":
        command = tool_input.get("command", "")
        return normalize_bash_command(command)

    if tool_name in ("write", "edit"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            return normalize_file_path(file_path, cwd)

    return None
