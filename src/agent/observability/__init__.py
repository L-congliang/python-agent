"""可观测性模块 - Trace 事件系统、Run Report、Checkpoint

提供 agent 运行时的完整可观测性:
- TraceEmitter: 事件流，记录每一步操作
- RunReporter: 运行报告生成
- CheckpointManager: 断点续传
- Redactor: 敏感信息脱敏
- WorkspaceSnapshot: 工作区快照
"""

from agent.observability.trace import TraceEmitter
from agent.observability.reporter import RunReporter
from agent.observability.checkpoint import CheckpointManager
from agent.observability.redactor import Redactor
from agent.observability.workspace import WorkspaceSnapshot

__all__ = [
    "TraceEmitter",
    "RunReporter",
    "CheckpointManager",
    "Redactor",
    "WorkspaceSnapshot",
]
