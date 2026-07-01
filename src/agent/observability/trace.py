"""Trace 事件系统 - 记录 agent 运行时的每一步操作

设计决策:
- 为什么用 JSONL 而不是 JSON？
  JSONL 每行独立，追加写入，中途崩溃已有数据不丢。
  JSON 必须等所有事件写完才能解析，中途崩溃数据全丢。

- 为什么每行都要 flush？
  确保事件立即写入磁盘，程序崩溃时不丢数据。

- 为什么用 ISO-8601 时间戳？
  标准格式，易于解析和排序，支持时区。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.observability.redactor import Redactor

logger = logging.getLogger("agent.observability.trace")


class TraceEmitter:
    """Trace 事件发射器

    将事件逐行追加到 trace.jsonl 文件。

    使用方式:
        emitter = TraceEmitter(Path(".agent/runs/run_abc123"))
        emitter.emit("run_started", {"user_request": "..."})
        emitter.emit("tool_executed", {"tool_name": "read", ...})
        emitter.close()
    """

    def __init__(self, run_dir: Path, run_id: str | None = None) -> None:
        """初始化 TraceEmitter

        Args:
            run_dir: 运行目录，trace.jsonl 会创建在此目录下
            run_id: 运行 ID，如果为 None 则自动生成
        """
        self._run_dir = run_dir
        self._run_dir.mkdir(parents=True, exist_ok=True)

        self._trace_file = run_dir / "trace.jsonl"
        self._run_id = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._redactor = Redactor()
        self._event_count = 0

        # 打开文件，追加模式
        self._file = open(self._trace_file, "a", encoding="utf-8")
        logger.info("TraceEmitter initialized: %s", self._trace_file)

    @property
    def run_id(self) -> str:
        """获取运行 ID"""
        return self._run_id

    @property
    def event_count(self) -> int:
        """获取已发射的事件数量"""
        return self._event_count

    def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        """发射一个事件

        Args:
            event: 事件类型（如 "run_started", "tool_executed"）
            data: 事件数据（可选）
        """
        record = {
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self._run_id,
            "data": data or {},
        }

        # 序列化为 JSON
        record_str = json.dumps(record, ensure_ascii=False)

        # 脱敏
        record_str = self._redactor.redact(record_str)

        # 写入文件
        self._file.write(record_str + "\n")
        self._file.flush()  # 确保立即写入磁盘

        self._event_count += 1
        logger.debug("Emitted event: %s", event)

    def close(self) -> None:
        """关闭 TraceEmitter"""
        if self._file and not self._file.closed:
            self._file.close()
            logger.info("TraceEmitter closed: %d events emitted", self._event_count)

    def __enter__(self) -> TraceEmitter:
        """支持 with 语句"""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """支持 with 语句"""
        self.close()
