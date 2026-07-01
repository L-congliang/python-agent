"""可观测性模块测试

测试覆盖:
- TraceEmitter: 事件发射、文件写入、脱敏
- RunReporter: 报告生成、工具调用记录
- CheckpointManager: checkpoint 创建、freshness 检测
- Redactor: 敏感信息脱敏
- WorkspaceSnapshot: 工作区快照
- SessionStore: 会话持久化
- RunStore: 运行目录管理
"""

import json
import tempfile
from pathlib import Path

import pytest

from agent.observability.trace import TraceEmitter
from agent.observability.reporter import RunReporter
from agent.observability.checkpoint import CheckpointManager, Checkpoint, TrackedFile, FreshnessResult
from agent.observability.redactor import Redactor
from agent.observability.workspace import WorkspaceSnapshot
from agent.persistence.session_store import SessionStore
from agent.persistence.run_store import RunStore


class TestTraceEmitter:
    """TraceEmitter 测试"""

    def test_emit_creates_file(self, tmp_path: Path) -> None:
        """emit 创建 trace.jsonl 文件"""
        emitter = TraceEmitter(tmp_path)
        emitter.emit("test_event", {"key": "value"})
        emitter.close()

        trace_file = tmp_path / "trace.jsonl"
        assert trace_file.exists()

    def test_emit_writes_jsonl(self, tmp_path: Path) -> None:
        """emit 写入 JSONL 格式"""
        emitter = TraceEmitter(tmp_path)
        emitter.emit("event_1", {"a": 1})
        emitter.emit("event_2", {"b": 2})
        emitter.close()

        trace_file = tmp_path / "trace.jsonl"
        lines = trace_file.read_text().strip().split("\n")
        assert len(lines) == 2

        # 解析每行 JSON
        for line in lines:
            data = json.loads(line)
            assert "event" in data
            assert "ts" in data
            assert "run_id" in data
            assert "data" in data

    def test_emit_increments_count(self, tmp_path: Path) -> None:
        """emit 递增事件计数"""
        emitter = TraceEmitter(tmp_path)
        assert emitter.event_count == 0

        emitter.emit("event_1")
        assert emitter.event_count == 1

        emitter.emit("event_2")
        assert emitter.event_count == 2

        emitter.close()

    def test_emit_redacts_sensitive_data(self, tmp_path: Path) -> None:
        """emit 自动脱敏敏感信息"""
        emitter = TraceEmitter(tmp_path)
        emitter.emit("test", {"api_key": "sk-abc123xyz1234567890"})
        emitter.close()

        trace_file = tmp_path / "trace.jsonl"
        content = trace_file.read_text()
        assert "sk-abc123xyz1234567890" not in content
        assert "<redacted>" in content

    def test_context_manager(self, tmp_path: Path) -> None:
        """支持 with 语句"""
        with TraceEmitter(tmp_path) as emitter:
            emitter.emit("test")

        trace_file = tmp_path / "trace.jsonl"
        assert trace_file.exists()

    def test_run_id_generation(self, tmp_path: Path) -> None:
        """自动生成 run_id"""
        emitter = TraceEmitter(tmp_path)
        assert emitter.run_id.startswith("run_")
        emitter.close()

    def test_custom_run_id(self, tmp_path: Path) -> None:
        """自定义 run_id"""
        emitter = TraceEmitter(tmp_path, run_id="custom_run_123")
        assert emitter.run_id == "custom_run_123"
        emitter.close()


class TestRunReporter:
    """RunReporter 测试"""

    def test_record_start(self, tmp_path: Path) -> None:
        """record_start 记录开始信息"""
        reporter = RunReporter(tmp_path)
        reporter.record_start("帮我改 main.py")

        report = reporter.report
        assert report["user_request"] == "帮我改 main.py"
        assert report["started_at"] is not None

    def test_record_tool_call(self, tmp_path: Path) -> None:
        """record_tool_call 记录工具调用"""
        reporter = RunReporter(tmp_path)
        reporter.record_start("test")
        reporter.record_tool_call("read", {"file_path": "main.py"}, 100, False)

        report = reporter.report
        assert report["total_tool_calls"] == 1
        assert len(report["tool_calls"]) == 1
        assert report["tool_calls"][0]["name"] == "read"
        assert report["tool_calls"][0]["duration_ms"] == 100

    def test_record_finish(self, tmp_path: Path) -> None:
        """record_finish 生成 report.json"""
        reporter = RunReporter(tmp_path)
        reporter.record_start("test")
        reporter.record_tool_call("read", {"file_path": "main.py"}, 100, False)
        reporter.record_finish("completed", "已完成")

        report_file = tmp_path / "report.json"
        assert report_file.exists()

        with open(report_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data["status"] == "completed"
        assert data["final_answer"] == "已完成"

    def test_record_tokens(self, tmp_path: Path) -> None:
        """record_tokens 记录 token 使用"""
        reporter = RunReporter(tmp_path)
        reporter.record_start("test")
        reporter.record_tokens(100, 50)
        reporter.record_tokens(200, 100)

        report = reporter.report
        assert report["total_tokens_used"] == 450  # 100+50+200+100

    def test_files_affected(self, tmp_path: Path) -> None:
        """记录受影响的文件"""
        reporter = RunReporter(tmp_path)
        reporter.record_start("test")
        reporter.record_tool_call("read", {"file_path": "main.py"}, 100, False)
        reporter.record_tool_call("edit", {"file_path": "main.py"}, 200, False)
        reporter.record_tool_call("read", {"file_path": "utils.py"}, 100, False)

        report = reporter.report
        assert "main.py" in report["files_affected"]
        assert "utils.py" in report["files_affected"]
        assert len(report["files_affected"]) == 2


class TestRedactor:
    """Redactor 测试"""

    def test_redact_api_key(self) -> None:
        """脱敏 API key"""
        redactor = Redactor()
        text = 'api_key: "sk-abc123xyz1234567890"'
        result = redactor.redact(text)
        assert "sk-abc123xyz1234567890" not in result
        assert "<redacted>" in result

    def test_redact_bearer_token(self) -> None:
        """脱敏 Bearer token"""
        redactor = Redactor()
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redactor.redact(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "Bearer <redacted>" in result

    def test_redact_env_var(self) -> None:
        """脱敏环境变量"""
        redactor = Redactor()
        text = "API_KEY=sk-abc123xyz SECRET_TOKEN=mytoken123"
        result = redactor.redact(text)
        assert "sk-abc123xyz" not in result
        assert "mytoken123" not in result

    def test_redact_dict(self) -> None:
        """脱敏字典中的值"""
        redactor = Redactor()
        data = {
            "api_key": "sk-abc123xyz1234567890abcdef",
            "safe_value": "hello",
            "nested": {
                "token": "Bearer eyJhbGciOiJIUzI1NiJ9",
            },
        }
        result = redactor.redact_dict(data)
        assert result["api_key"] != data["api_key"]
        assert result["safe_value"] == "hello"
        assert "<redacted>" in result["nested"]["token"]

    def test_redact_preserves_safe_text(self) -> None:
        """不改变安全文本"""
        redactor = Redactor()
        text = "Hello, this is a normal text without secrets."
        result = redactor.redact(text)
        assert result == text


class TestCheckpointManager:
    """CheckpointManager 测试"""

    def test_create_checkpoint(self, tmp_path: Path) -> None:
        """创建 checkpoint"""
        mgr = CheckpointManager(tmp_path)
        mgr.track_file(__file__, "read")

        checkpoint = mgr.create(
            goal="测试",
            completed_steps=["步骤1"],
            next_step="步骤2",
            run_id="test_run",
        )

        assert checkpoint.goal == "测试"
        assert checkpoint.completed_steps == ["步骤1"]
        assert checkpoint.next_step == "步骤2"
        assert checkpoint.run_id == "test_run"
        assert len(checkpoint.tracked_files) > 0

    def test_save_and_load_checkpoint(self, tmp_path: Path) -> None:
        """保存和加载 checkpoint"""
        mgr = CheckpointManager(tmp_path)
        mgr.track_file(__file__, "read")

        checkpoint = mgr.create(
            goal="测试",
            completed_steps=["步骤1"],
            next_step="步骤2",
        )

        # 加载最新的 checkpoint
        loaded = mgr.load_latest()
        assert loaded is not None
        assert loaded.goal == "测试"
        assert loaded.completed_steps == ["步骤1"]

    def test_check_freshness_unchanged(self, tmp_path: Path) -> None:
        """文件未变化时 freshness 为 full-valid"""
        mgr = CheckpointManager(tmp_path)
        mgr.track_file(__file__, "read")

        checkpoint = mgr.create(
            goal="测试",
            completed_steps=[],
            next_step="继续",
        )

        result = mgr.check_freshness(checkpoint)
        assert result.resume_status == "full-valid"

    def test_check_freshness_modified(self, tmp_path: Path) -> None:
        """文件变化时 freshness 为 partial-stale"""
        mgr = CheckpointManager(tmp_path)

        # 创建一个临时文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")
        mgr.track_file(str(test_file), "read")

        checkpoint = mgr.create(
            goal="测试",
            completed_steps=[],
            next_step="继续",
        )

        # 修改文件
        test_file.write_text("modified")

        result = mgr.check_freshness(checkpoint)
        assert result.resume_status == "partial-stale"
        assert result.file_statuses[str(test_file)] == "modified"

    def test_check_freshness_deleted(self, tmp_path: Path) -> None:
        """文件删除时 freshness 为 invalid"""
        mgr = CheckpointManager(tmp_path)

        # 创建一个临时文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")
        mgr.track_file(str(test_file), "read")

        checkpoint = mgr.create(
            goal="测试",
            completed_steps=[],
            next_step="继续",
        )

        # 删除文件
        test_file.unlink()

        result = mgr.check_freshness(checkpoint)
        assert result.resume_status == "invalid"
        assert result.file_statuses[str(test_file)] == "deleted"


class TestWorkspaceSnapshot:
    """WorkspaceSnapshot 测试"""

    def test_capture_git_info(self, tmp_path: Path) -> None:
        """捕获 git 信息"""
        snapshot = WorkspaceSnapshot(tmp_path)
        info = snapshot.capture()

        assert "workspace_root" in info
        assert "git_branch" in info
        assert "recent_commits" in info
        assert "project_docs" in info

    def test_capture_project_docs(self, tmp_path: Path) -> None:
        """捕获项目文档"""
        # 创建测试文档
        readme = tmp_path / "README.md"
        readme.write_text("# Test Project\nThis is a test.")

        snapshot = WorkspaceSnapshot(tmp_path)
        info = snapshot.capture()

        assert "README.md" in info["project_docs"]
        assert "# Test Project" in info["project_docs"]["README.md"]


class TestSessionStore:
    """SessionStore 测试"""

    def test_save_and_load(self, tmp_path: Path) -> None:
        """保存和加载会话"""
        store = SessionStore(tmp_path)

        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
        ]

        session_id = store.save(messages, memory={"task": "测试"})
        assert session_id is not None

        loaded = store.load(session_id)
        assert loaded is not None
        assert len(loaded["messages"]) == 2
        assert loaded["memory"]["task"] == "测试"

    def test_load_latest(self, tmp_path: Path) -> None:
        """加载最新会话"""
        import time

        store = SessionStore(tmp_path)

        session_id_1 = store.save([{"role": "user", "content": "第一条"}])
        time.sleep(0.1)  # 确保不同的 mtime
        session_id_2 = store.save([{"role": "user", "content": "第二条"}])

        latest = store.load_latest()
        assert latest is not None
        # 最新的会话应该是 session_id_2
        assert latest["id"] == session_id_2

    def test_list_sessions(self, tmp_path: Path) -> None:
        """列出所有会话"""
        store = SessionStore(tmp_path)

        store.save([{"role": "user", "content": "会话1"}])
        store.save([{"role": "user", "content": "会话2"}])

        sessions = store.list_sessions()
        assert len(sessions) == 2

    def test_delete_session(self, tmp_path: Path) -> None:
        """删除会话"""
        store = SessionStore(tmp_path)

        session_id = store.save([{"role": "user", "content": "测试"}])
        assert store.load(session_id) is not None

        store.delete(session_id)
        assert store.load(session_id) is None


class TestRunStore:
    """RunStore 测试"""

    def test_create_run_dir(self, tmp_path: Path) -> None:
        """创建运行目录"""
        store = RunStore(tmp_path)
        run_dir = store.create_run_dir("test_run")

        assert run_dir.exists()
        assert run_dir.name == "test_run"

    def test_list_runs(self, tmp_path: Path) -> None:
        """列出所有运行"""
        store = RunStore(tmp_path)

        store.create_run_dir("run_1")
        store.create_run_dir("run_2")

        runs = store.list_runs()
        assert len(runs) == 2

    def test_cleanup(self, tmp_path: Path) -> None:
        """清理旧运行"""
        store = RunStore(tmp_path)

        # 创建多个运行
        for i in range(5):
            store.create_run_dir(f"run_{i}")

        # 保留最近 2 个
        cleaned = store.cleanup(keep_last=2)
        assert cleaned == 3

        runs = store.list_runs()
        assert len(runs) == 2
