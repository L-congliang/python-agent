"""权限系统 - 通用权限策略层

对齐 Claude Code 的权限系统设计：
- PermissionMode: 权限模式（default、plan）
- PermissionChecker: 权限检查器，管理模式和策略判断
- check_system_policy: 系统级策略判断函数
"""

from agent.permissions.checker import (
    PermissionChecker,
    PermissionMode,
    check_system_policy,
)

__all__ = [
    "PermissionChecker",
    "PermissionMode",
    "check_system_policy",
]
