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
            "task_id": None,
            "model": None,
            "provider": None,
            "status": None,
            "stop_reason": None,
            "final_answer": None,
            "tool_calls": [],
            "duration_ms": None,
            "total_turns": 0,
            "total_tool_calls": 0,
            "total_tokens_used": 0,
            "files_affected": [],
            "files_read": [],
            "files_written": [],
            "total_bytes_read": 0,
            "total_bytes_written": 0,
            "total_artifacts": 0,
            "permission_asks": 0,
            "permission_allows": 0,
            "permission_denies": 0,
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
        *,
        turn_index: int | None = None,
        permission_decision: str | None = None,
        error_type: str | None = None,
        bytes_read: int | None = None,
        bytes_written: int | None = None,
        files_read: list[str] | None = None,
        files_written: list[str] | None = None,
        diff_summary: str | None = None,
        artifact_path: str | None = None,
        artifact_size: int | None = None,
    ) -> None:
        """记录工具调用

        Args:
            tool_name: 工具名称
            tool_args: 工具参数（摘要，不过长）
            duration_ms: 执行耗时（毫秒）
            is_error: 是否出错
            error_message: 错误信息（可选）
            turn_index: 轮次索引
            permission_decision: 权限决策 (allow/deny/ask/none)
            error_type: 错误类型 (validation_error/timeout/not_found/permission_denied 等)
            bytes_read: 读取字节数
            bytes_written: 写入字节数
            files_read: 本次读取的文件列表
            files_written: 本次写入的文件列表
            diff_summary: diff 摘要（适用于 edit 操作）
            artifact_path: artifact 文件路径
            artifact_size: artifact 文件大小
        """
        # 构造输入摘要（避免泄露过长内容）
        input_summary = {}
        for key, value in tool_args.items():
            if isinstance(value, str) and len(value) > 200:
                input_summary[key] = value[:200] + "..."
            else:
                input_summary[key] = value

        tool_call: dict[str, Any] = {
            "name": tool_name,
            "input_summary": input_summary,
            "duration_ms": duration_ms,
            "is_error": is_error,
        }
        if turn_index is not None:
            tool_call["turn_index"] = turn_index
        if error_message:
            tool_call["error_message"] = error_message
        if error_type:
            tool_call["error_type"] = error_type
        if permission_decision:
            tool_call["permission_decision"] = permission_decision
        if bytes_read is not None:
            tool_call["bytes_read"] = bytes_read
        if bytes_written is not None:
            tool_call["bytes_written"] = bytes_written
        if files_read:
            tool_call["files_read"] = files_read
        if files_written:
            tool_call["files_written"] = files_written
        if diff_summary:
            tool_call["diff_summary"] = diff_summary
        if artifact_path:
            tool_call["artifact_path"] = artifact_path
        if artifact_size is not None:
            tool_call["artifact_size"] = artifact_size

        self._report["tool_calls"].append(tool_call)
        self._report["total_tool_calls"] += 1

        # 累计字节数
        if bytes_read:
            self._report["total_bytes_read"] += bytes_read
        if bytes_written:
            self._report["total_bytes_written"] += bytes_written
        if artifact_path:
            self._report["total_artifacts"] += 1

        # 记录受影响的文件
        file_path = tool_args.get("file_path") or tool_args.get("path")
        if file_path and file_path not in self._report["files_affected"]:
            self._report["files_affected"].append(file_path)

        # 记录读/写的文件
        if files_read:
            for f in files_read:
                if f not in self._report["files_read"]:
                    self._report["files_read"].append(f)
        if files_written:
            for f in files_written:
                if f not in self._report["files_written"]:
                    self._report["files_written"].append(f)

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

    def record_permission(self, decision: str) -> None:
        """记录权限决策

        Args:
            decision: "ask" | "allow" | "deny"
        """
        if decision == "ask":
            self._report["permission_asks"] += 1
        elif decision == "allow":
            self._report["permission_allows"] += 1
        elif decision == "deny":
            self._report["permission_denies"] += 1

    def set_run_metadata(self, **kwargs: Any) -> None:
        """设置运行级别元数据（task_id, model, provider 等）"""
        for key, value in kwargs.items():
            if key in self._report:
                self._report[key] = value

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

        # 计算聚合指标
        self._report["aggregate"] = self._compute_aggregates()

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

    def _compute_aggregates(self) -> dict[str, Any]:
        """计算聚合指标"""
        tool_calls = self._report["tool_calls"]
        total = len(tool_calls)
        if total == 0:
            return {
                "tool_success_rate": 1.0,
                "tool_failure_count": 0,
                "p50_latency_ms": 0,
                "p95_latency_ms": 0,
                "max_latency_ms": 0,
                "permission_allow_rate": 1.0,
                "permission_deny_count": self._report["permission_denies"],
            }

        # tool success rate
        errors = sum(1 for tc in tool_calls if tc.get("is_error"))
        success_rate = (total - errors) / total

        # latency percentiles (nearest-rank method)
        latencies = sorted(tc.get("duration_ms", 0) for tc in tool_calls)
        p50_idx = min(round(len(latencies) * 0.5) - 1, len(latencies) - 1) if latencies else 0
        p95_idx = min(round(len(latencies) * 0.95) - 1, len(latencies) - 1) if latencies else 0
        p50_idx = max(p50_idx, 0)
        p95_idx = max(p95_idx, 0)

        # permission rate
        asks = self._report["permission_asks"]
        allows = self._report["permission_allows"]
        denies = self._report["permission_denies"]
        perm_total = asks + allows + denies
        allow_rate = allows / perm_total if perm_total > 0 else 1.0

        return {
            "tool_success_rate": round(success_rate, 4),
            "tool_failure_count": errors,
            "p50_latency_ms": latencies[p50_idx] if latencies else 0,
            "p95_latency_ms": latencies[p95_idx] if latencies else 0,
            "max_latency_ms": latencies[-1] if latencies else 0,
            "permission_allow_rate": round(allow_rate, 4),
            "permission_deny_count": self._report["permission_denies"],
        }

    @property
    def report(self) -> dict[str, Any]:
        """获取当前报告数据（只读副本）"""
        return self._report.copy()

    def generate_summary_markdown(self) -> str:
        """生成 Markdown 格式的运行摘要"""
        r = self._report
        agg = r.get("aggregate", {})
        lines = [
            f"# Run Summary: {r['run_id']}",
            "",
            f"- **Status**: {r.get('status', 'unknown')}",
            f"- **Duration**: {r.get('duration_ms', 0)}ms",
            f"- **Turns**: {r.get('total_turns', 0)}",
            f"- **Tool Calls**: {r.get('total_tool_calls', 0)}",
            f"- **Tokens Used**: {r.get('total_tokens_used', 0)}",
            "",
            "## Tool Metrics",
            "",
            f"- Tool Success Rate: {agg.get('tool_success_rate', 'N/A')}",
            f"- Tool Failures: {agg.get('tool_failure_count', 0)}",
            f"- P50 Latency: {agg.get('p50_latency_ms', 0)}ms",
            f"- P95 Latency: {agg.get('p95_latency_ms', 0)}ms",
            f"- Max Latency: {agg.get('max_latency_ms', 0)}ms",
            "",
            "## File Metrics",
            "",
            f"- Files Affected: {len(r.get('files_affected', []))}",
            f"- Files Read: {len(r.get('files_read', []))}",
            f"- Files Written: {len(r.get('files_written', []))}",
            f"- Total Bytes Read: {r.get('total_bytes_read', 0)}",
            f"- Total Bytes Written: {r.get('total_bytes_written', 0)}",
            f"- Artifacts Generated: {r.get('total_artifacts', 0)}",
            "",
            "## Permission Metrics",
            "",
            f"- Permission Asks: {r.get('permission_asks', 0)}",
            f"- Permission Allows: {r.get('permission_allows', 0)}",
            f"- Permission Denies: {r.get('permission_denies', 0)}",
            f"- Allow Rate: {agg.get('permission_allow_rate', 'N/A')}",
        ]
        return "\n".join(lines)
