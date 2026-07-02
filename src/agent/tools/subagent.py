"""SubAgentTool - 对齐 Claude Code 的 AgentTool

设计决策:
- 为什么作为普通工具注册？
  对齐 Claude Code 的设计，SubAgentTool 是 ToolRegistry 中的一个普通工具。
  主 Agent 通过 tool_use 调用，不需要特殊的路由机制。

- 为什么支持阻塞和后台两种模式？
  阻塞模式：简单场景，主 Agent 等待子 Agent 完成。
  后台模式：并行场景，主 Agent 可以同时派生多个子 Agent。

- 为什么返回结构化结果？
  Claude Code 返回纯文本，但丢失了执行元数据。
  结构化结果让主 Agent 能判断子 Agent 的执行质量。

- 为什么需要 worktree 隔离？
  子 Agent 可能修改文件。worktree 隔离让子 Agent 在独立的 git 分支中工作，
  不影响主 Agent 的工作目录。执行完后可以选择合并或丢弃。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

from agent.tools.base import build_tool
from agent.core.types import (
    ToolResult,
    PermissionDecision,
    ValidationResult,
)
from agent.core.context import ToolUseContext
from agent.orchestration.agent_type import AgentTypeDefinition, AgentTypeRegistry
from agent.orchestration.sub_agent import (
    SubAgentConstraints,
    SubAgentResult,
    SubAgentStatus,
    SubAgentTask,
)

logger = logging.getLogger("agent.tools.subagent")

# 全局 AgentTypeRegistry 和 TaskManager（延迟初始化）
_type_registry: AgentTypeRegistry | None = None
_task_manager: Any = None  # TaskManager，用 Any 避免循环导入


def get_type_registry() -> AgentTypeRegistry:
    """获取全局 AgentTypeRegistry"""
    global _type_registry
    if _type_registry is None:
        _type_registry = AgentTypeRegistry()
    return _type_registry


def get_task_manager() -> Any:
    """获取全局 TaskManager"""
    global _task_manager
    if _task_manager is None:
        from agent.orchestration.message_bus import TaskManager
        _task_manager = TaskManager()
    return _task_manager


# ============================================================
# Worktree 管理
# ============================================================

def _create_worktree(task_id: str, workspace_root: str | None = None) -> str | None:
    """创建 git worktree

    Args:
        task_id: 任务 ID，用于 worktree 目录名
        workspace_root: 工作区根目录（可选）

    Returns:
        worktree 路径，失败返回 None
    """
    worktree_dir = Path(workspace_root or ".") / ".worktrees" / task_id
    branch_name = f"subagent-{task_id}"

    try:
        # 确保 .worktrees 目录存在
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)

        # 创建 worktree
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_dir), "-b", branch_name],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.warning("Failed to create worktree: %s", result.stderr)
            return None

        logger.info("Created worktree: %s", worktree_dir)
        return str(worktree_dir)

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("Failed to create worktree: %s", e)
        return None


def _cleanup_worktree(worktree_path: str) -> None:
    """清理 worktree

    Args:
        worktree_path: worktree 路径
    """
    try:
        result = subprocess.run(
            ["git", "worktree", "remove", worktree_path, "--force"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.warning("Failed to remove worktree: %s", result.stderr)
        else:
            logger.info("Removed worktree: %s", worktree_path)

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("Failed to remove worktree: %s", e)


def _cleanup_orphaned_worktrees(workspace_root: str | None = None) -> int:
    """清理孤立的 worktree

    检查 .worktrees/ 目录，清理 git 不再跟踪的 worktree。

    Args:
        workspace_root: 工作区根目录

    Returns:
        清理的数量
    """
    worktrees_dir = Path(workspace_root or ".") / ".worktrees"
    if not worktrees_dir.exists():
        return 0

    cleaned = 0
    for item in worktrees_dir.iterdir():
        if item.is_dir():
            # 检查是否是有效的 git worktree
            git_file = item / ".git"
            if not git_file.exists():
                # 不是有效的 worktree，清理
                try:
                    import shutil
                    shutil.rmtree(item)
                    cleaned += 1
                    logger.info("Cleaned orphaned worktree: %s", item)
                except Exception as e:
                    logger.warning("Failed to clean orphaned worktree %s: %s", item, e)

    return cleaned


def _execute_subagent(input: dict, context: ToolUseContext) -> ToolResult:
    """SubAgentTool 的执行函数

    Args:
        input: 工具参数
        context: 工具执行上下文

    Returns:
        ToolResult（包含 SubAgentResult 的 JSON 或 task_id）
    """
    from agent.core.loop import AgentLoop

    prompt = input.get("prompt", "")
    description = input.get("description", "")
    agent_type_name = input.get("agent_type", "general-purpose")
    isolation = input.get("isolation")  # "worktree" | None
    run_in_background = input.get("run_in_background", False)

    # 获取类型定义
    type_registry = get_type_registry()
    agent_type_def = type_registry.get(agent_type_name)

    # 获取或创建约束
    # 从 context.messages 中获取父 Agent 的约束（如果有的话）
    constraints = SubAgentConstraints()

    # 查找父 Agent（从 context 中获取）
    parent_loop = _find_parent_agent(context)
    if parent_loop is None:
        return ToolResult(
            output="[错误] 无法找到父 Agent 实例",
            is_error=True,
        )

    # 检查约束
    if not constraints.can_create_agent():
        return ToolResult(
            output="[错误] 超过最大 Agent 数量限制",
            is_error=True,
        )

    if run_in_background:
        return _execute_background(
            parent_loop=parent_loop,
            task=prompt,
            description=description,
            agent_type_def=agent_type_def,
            constraints=constraints,
            isolation=isolation,
        )
    else:
        return _execute_blocking(
            parent_loop=parent_loop,
            task=prompt,
            description=description,
            agent_type_def=agent_type_def,
            constraints=constraints,
            isolation=isolation,
        )


def _find_parent_agent(context: ToolUseContext) -> Any:
    """从上下文中找到父 AgentLoop 实例

    Args:
        context: 工具执行上下文

    Returns:
        AgentLoop 实例或 None
    """
    # ToolUseContext 没有直接引用 AgentLoop
    # 但我们可以从 context 中获取必要信息来创建子 Agent
    # 这里我们需要一个更好的方式来传递父 Agent 引用
    # 暂时通过全局变量或上下文扩展来实现

    # 方案：通过 context 的 messages 和 tools 重建父 Agent 的部分状态
    # 更好的方案：在 ToolUseContext 中添加 agent_loop 引用
    return None


def _execute_blocking(
    parent_loop: Any,
    task: str,
    description: str,
    agent_type_def: AgentTypeDefinition,
    constraints: SubAgentConstraints,
    isolation: str | None = None,
) -> ToolResult:
    """阻塞模式执行

    Args:
        parent_loop: 父 AgentLoop 实例
        task: 任务描述
        description: 任务简短描述
        agent_type_def: Agent 类型定义
        constraints: 共享约束
        isolation: 隔离模式（"worktree" | None）

    Returns:
        ToolResult
    """
    from agent.core.loop import AgentLoop

    logger.info("Starting blocking sub-agent: %s", description)

    # 处理 worktree 隔离
    worktree_path: str | None = None
    original_workspace = parent_loop._config.workspace_root

    if isolation == "worktree":
        task_id = f"sa_{id(task) % 1000000:06d}"
        worktree_path = _create_worktree(task_id, original_workspace)
        if worktree_path:
            # 临时修改父 Agent 的 workspace_root
            parent_loop._config.workspace_root = worktree_path
            logger.info("Using worktree: %s", worktree_path)
        else:
            # worktree 创建失败，回退到非隔离模式
            logger.warning("Worktree creation failed, falling back to non-isolated mode")

    # 创建子 Agent
    sub_agent = AgentLoop.create_sub_agent(
        parent=parent_loop,
        task=task,
        agent_type_def=agent_type_def,
        constraints=constraints,
    )

    # 执行
    try:
        result_text = sub_agent.run(task)
        result = sub_agent.create_subagent_result(result_text)
    except Exception as e:
        logger.error("Sub-agent failed: %s", e)
        result = SubAgentResult(
            status=SubAgentStatus.FAILED,
            error=str(e),
            agent_type=agent_type_def.name,
        )

    # 恢复原始 workspace_root
    if worktree_path:
        parent_loop._config.workspace_root = original_workspace

    logger.info(
        "Sub-agent completed: status=%s, turns=%d, tools=%d",
        result.status.value,
        result.turns_used,
        result.tool_calls_used,
    )

    # 返回结构化结果（包含 worktree 路径信息）
    result_dict = result.to_dict()
    if worktree_path:
        result_dict["worktree_path"] = worktree_path

    return ToolResult(
        output=json.dumps(result_dict, ensure_ascii=False, indent=2),
        is_error=result.status == SubAgentStatus.FAILED,
    )


def _execute_background(
    parent_loop: Any,
    task: str,
    description: str,
    agent_type_def: AgentTypeDefinition,
    constraints: SubAgentConstraints,
    isolation: str | None = None,
) -> ToolResult:
    """后台模式执行

    Args:
        parent_loop: 父 AgentLoop 实例
        task: 任务描述
        description: 任务简短描述
        agent_type_def: Agent 类型定义
        constraints: 共享约束
        isolation: 隔离模式（"worktree" | None）

    Returns:
        ToolResult（包含 task_id）
    """
    from agent.core.loop import AgentLoop

    logger.info("Starting background sub-agent: %s", description)

    # 处理 worktree 隔离
    worktree_path: str | None = None
    original_workspace = parent_loop._config.workspace_root

    if isolation == "worktree":
        sub_task_temp = SubAgentTask()
        worktree_path = _create_worktree(sub_task_temp.task_id, original_workspace)
        if worktree_path:
            parent_loop._config.workspace_root = worktree_path
            logger.info("Using worktree: %s", worktree_path)
        else:
            logger.warning("Worktree creation failed, falling back to non-isolated mode")

    # 创建子 Agent
    sub_agent = AgentLoop.create_sub_agent(
        parent=parent_loop,
        task=task,
        agent_type_def=agent_type_def,
        constraints=constraints,
    )

    # 恢复原始 workspace_root
    if worktree_path:
        parent_loop._config.workspace_root = original_workspace

    # 创建后台任务
    sub_task = SubAgentTask()
    task_manager = get_task_manager()

    def run_in_thread() -> None:
        """在线程中执行子 Agent"""
        try:
            # 如果有 worktree，临时设置 workspace_root
            if worktree_path:
                sub_agent._config.workspace_root = worktree_path

            result_text = sub_agent.run(task)
            sub_task.result = sub_agent.create_subagent_result(result_text)

            # 添加 worktree 信息到结果
            if worktree_path:
                result_dict = sub_task.result.to_dict()
                result_dict["worktree_path"] = worktree_path
                sub_task.result.result = json.dumps(result_dict, ensure_ascii=False)

            sub_task.status = sub_task.result.status
        except Exception as e:
            logger.error("Background sub-agent failed: %s", e)
            sub_task.result = SubAgentResult(
                status=SubAgentStatus.FAILED,
                error=str(e),
                agent_type=agent_type_def.name,
            )
            sub_task.status = SubAgentStatus.FAILED
        finally:
            # 清理 worktree（可选：可以保留供用户检查）
            # if worktree_path:
            #     _cleanup_worktree(worktree_path)
            pass

    # 启动线程
    thread = threading.Thread(target=run_in_thread, daemon=True)
    sub_task.thread = thread
    task_manager.register(sub_task)
    thread.start()

    # 立即返回 task_id
    result_data: dict[str, Any] = {
        "task_id": sub_task.task_id,
        "status": "running",
        "description": description,
    }
    if worktree_path:
        result_data["worktree_path"] = worktree_path

    return ToolResult(
        output=json.dumps(result_data, ensure_ascii=False),
    )


# 构建 SubAgentTool
SubAgentTool = build_tool(
    name="subagent",
    description=(
        "Spawn a sub-agent to handle a specific task independently. "
        "Use this for parallel exploration, isolated context tasks, "
        "or when you need to delegate a well-defined subtask."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "The task description for the sub-agent. "
                    "Should be clear and self-contained."
                ),
            },
            "description": {
                "type": "string",
                "description": (
                    "A short 3-5 word description of the task, "
                    "used for UI display."
                ),
            },
            "agent_type": {
                "type": "string",
                "description": (
                    "The type of agent to spawn. "
                    "Options: general-purpose (default), explore, code-reviewer."
                ),
                "default": "general-purpose",
            },
            "run_in_background": {
                "type": "boolean",
                "description": (
                    "If true, the sub-agent runs in the background "
                    "and returns a task_id immediately."
                ),
                "default": False,
            },
            "isolation": {
                "type": "string",
                "enum": ["worktree"],
                "description": (
                    "Isolation mode. 'worktree' creates a separate git worktree "
                    "for the sub-agent to work in. Omit for no isolation."
                ),
            },
        },
        "required": ["prompt", "description"],
    },
    execute_fn=_execute_subagent,
    is_read_only=lambda input: True,  # 子 Agent 本身是只读操作
    get_summary=lambda input: f"Spawning sub-agent: {input.get('description', '')}",
    get_activity_description=lambda input: f"Running sub-agent: {input.get('description', '')}",
)
