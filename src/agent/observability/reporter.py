"""Run Report 生成器 - 每次运行结束生成完整报告

设计决策:
- 为什么用 JSON 格式？
  结构化数据，易于解析和对比。
  可以用 jq 或 Python 脚本分析。

- 为什么在运行结束时生成？
  避免运行中频繁写入影响性能。
  运行结束时数据最完整。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.observability.redactor import Redactor

logger = logging.getLogger("agent.observability.reporter")


class RunReporter:
    """Run Report 生成器

    在运行结束时生成 report.json，记录完整运行快照。

    使用方式:
        reporter = RunReporter(Path(".agent/runs/run_abc123"))
        reporter.record_start(user_request="帮我改 main.py")
        reporter.record_tool_call("read", {"file_path": "main.py"}, 100, False)
        reporter.record_tool_call("edit", {"file_path": "main.py"}, 200, False)
        reporter.record_finish("completed", "已将 print 替换为 logging")
    """

    def __init__(self, run_dir: Path, run_id: str | None = None) -> None:
        """初始化 RunReporter

        Args:
            run_dir: 运行目录，report.json 会创建在此目录下
            run_id: 运行 ID，如果为 None 则自动生成
        """
        self._run_dir = run_dir
        self._run_dir.mkdir(parents=True, exist_ok=True)

        self._report_file = run_dir / "report.json"
        self._run_id = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._redactor = Redactor()

        # 报告数据
        self._report: dict[str, Any] = {
            "run_id": self._run_id,
            "started_at": None,
            "finished_at": None,
            "user_request": None,
            "status": None,
            "stop_reason": None,
            "final_answer": None,
            "tool_calls": [],
            "duration_ms": None,
            "total_turns": 0,
            "total_tool_calls": 0,
            "total_tokens_used": 0,
            "files_affected": [],
            "error": None,
        }

        self._start_time: datetime | None = None
        logger.info("RunReporter initialized: %s", self._report_file)

    def record_start(self, user_request: str) -> None:
        """记录运行开始

        Args:
            user_request: 用户输入的请求
        """
        self._start_time = datetime.now(timezone.utc)
        self._report["started_at"] = self._start_time.isoformat()
        self._report["user_request"] = user_request
        logger.debug("Run started: %s", user_request[:50])

    def record_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        duration_ms: int,
        is_error: bool,
        error_message: str | None = None,
    ) -> None:
        """记录工具调用

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            duration_ms: 执行耗时（毫秒）
            is_error: 是否出错
            error_message: 错误信息（可选）
        """
        tool_call = {
            "name": tool_name,
            "args": tool_args,
            "duration_ms": duration_ms,
            "is_error": is_error,
            "error_message": error_message,
        }
        self._report["tool_calls"].append(tool_call)
        self._report["total_tool_calls"] += 1

        # 记录受影响的文件
        file_path = tool_args.get("file_path") or tool_args.get("path")
        if file_path and file_path not in self._report["files_affected"]:
            self._report["files_affected"].append(file_path)

        logger.debug("Tool call recorded: %s (%dms)", tool_name, duration_ms)

    def record_turn(self) -> None:
        """记录一轮对话"""
        self._report["total_turns"] += 1

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """记录 token 使用

        Args:
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数
        """
        self._report["total_tokens_used"] += input_tokens + output_tokens

    def record_finish(
        self,
        status: str,
        final_answer: str | None = None,
        stop_reason: str | None = None,
        error: str | None = None,
    ) -> None:
        """记录运行结束

        Args:
            status: 最终状态（completed / failed / stopped）
            final_answer: 最终回复（可选）
            stop_reason: 停止原因（可选）
            error: 错误信息（可选）
        """
        finish_time = datetime.now(timezone.utc)
        self._report["finished_at"] = finish_time.isoformat()
        self._report["status"] = status
        self._report["final_answer"] = final_answer
        self._report["stop_reason"] = stop_reason
        self._report["error"] = error

        # 计算总耗时
        if self._start_time:
            duration = finish_time - self._start_time
            self._report["duration_ms"] = int(duration.total_seconds() * 1000)

        # 脱敏
        report_safe = self._redactor.redact_dict(self._report)

        # 写入文件
        with open(self._report_file, "w", encoding="utf-8") as f:
            json.dump(report_safe, f, ensure_ascii=False, indent=2)

        logger.info(
            "Run finished: status=%s, duration=%sms, tool_calls=%d",
            status,
            self._report["duration_ms"],
            self._report["total_tool_calls"],
        )

    @property
    def report(self) -> dict[str, Any]:
        """获取当前报告数据（只读副本）"""
        return self._report.copy()
