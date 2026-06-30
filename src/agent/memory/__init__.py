"""分层记忆系统 - 管理 agent 的工作记忆和持久记忆

设计决策:
- 为什么分层？
  工作记忆（WorkingMemory）：当前 session 的临时信息，速度快
  文件摘要（FileSummaries）：避免重复读取文件
  事件笔记（EpisodicNotes）：带时间戳的事件记录
  持久记忆（DurableMemory）：跨 session 的重要信息

- 为什么用 LRU？
  recent_files 用 LRU 保证最近访问的文件优先保留
  符合"最近使用的文件最可能再次使用"的假设

- 为什么文件摘要只保留 180 字符？
  足够识别文件用途，又不会占用太多 token
  Claude Code 也用类似长度
"""

from agent.memory.working import WorkingMemory
from agent.memory.file_summaries import FileSummaries, FileSummary
from agent.memory.episodic import EpisodicNotes, Note
from agent.memory.durable import DurableMemory
from agent.memory.retrieval import Retrieval
from agent.memory.renderer import MemoryRenderer
from agent.memory.manager import MemoryManager

__all__ = [
    "WorkingMemory",
    "FileSummaries",
    "FileSummary",
    "EpisodicNotes",
    "Note",
    "DurableMemory",
    "Retrieval",
    "MemoryRenderer",
    "MemoryManager",
]
