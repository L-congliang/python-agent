"""Session 持久化 - 保存和恢复对话历史

设计决策:
- 为什么用 JSON 格式？
  人类可读，易于调试。
  结构化数据，易于解析。

- 为什么自动保存？
  避免丢失重要信息。
  简化使用流程。

- 为什么支持 --resume？
  用户可能想继续上次的对话。
  长任务中断后可以恢复。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.observability.redactor import Redactor

logger = logging.getLogger("agent.persistence.session_store")


class SessionStore:
    """Session 持久化存储

    管理会话的保存、加载和恢复。

    使用方式:
        store = SessionStore(Path(".agent/sessions"))
        session_id = store.save(
            messages=[...],
            memory={...},
            workspace_root="/path/to/project",
        )
        # 恢复时
        session = store.load_latest()
        if session:
            messages = session["messages"]
            memory = session["memory"]
    """

    def __init__(self, session_dir: Path) -> None:
        """初始化 SessionStore

        Args:
            session_dir: session 存储目录
        """
        self._session_dir = session_dir
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._redactor = Redactor()
        logger.info("SessionStore initialized: %s", session_dir)

    def save(
        self,
        messages: list[dict[str, Any]],
        memory: dict[str, Any] | None = None,
        workspace_root: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """保存会话

        Args:
            messages: 消息历史
            memory: 记忆状态（可选）
            workspace_root: 工作区根目录（可选）
            session_id: 会话 ID（可选，自动生成）

        Returns:
            会话 ID
        """
        session_id = session_id or f"session_{uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat()

        session_data = {
            "id": session_id,
            "created_at": created_at,
            "workspace_root": workspace_root,
            "messages": messages,
            "memory": memory or {},
        }

        # 脱敏
        session_safe = self._redactor.redact_dict(session_data)

        # 保存
        file_path = self._session_dir / f"{session_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(session_safe, f, ensure_ascii=False, indent=2)

        logger.info("Session saved: %s", session_id)
        return session_id

    def load(self, session_id: str) -> dict[str, Any] | None:
        """加载指定会话

        Args:
            session_id: 会话 ID

        Returns:
            会话数据，如果不存在则返回 None
        """
        file_path = self._session_dir / f"{session_id}.json"
        if not file_path.exists():
            logger.warning("Session not found: %s", session_id)
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)

        logger.info("Session loaded: %s", session_id)
        return data

    def load_latest(self) -> dict[str, Any] | None:
        """加载最新的会话

        Returns:
            最新的会话数据，如果没有则返回 None
        """
        session_files = sorted(
            self._session_dir.glob("session_*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        if not session_files:
            logger.info("No session found")
            return None

        result = self.load(session_files[0].stem)
        return result

    def list_sessions(self) -> list[dict[str, Any]]:
        """列出所有会话

        Returns:
            会话摘要列表
        """
        sessions = []
        for file_path in sorted(
            self._session_dir.glob("session_*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        ):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append({
                    "id": data.get("id"),
                    "created_at": data.get("created_at"),
                    "workspace_root": data.get("workspace_root"),
                    "message_count": len(data.get("messages", [])),
                })
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to parse session %s: %s", file_path, e)

        return sessions

    def delete(self, session_id: str) -> bool:
        """删除会话

        Args:
            session_id: 会话 ID

        Returns:
            是否成功删除
        """
        file_path = self._session_dir / f"{session_id}.json"
        if not file_path.exists():
            logger.warning("Session not found: %s", session_id)
            return False

        file_path.unlink()
        logger.info("Session deleted: %s", session_id)
        return True
