"""Edit History Store - 文件编辑历史持久化

记录 write/edit 工具的修改历史，支持 backup 和 rollback。

设计决策:
- 为什么需要持久化？
  session 结束后仍需保留历史记录，方便回溯和恢复。
  备份文件和 history 记录都保存在磁盘上，不随 session 消失。

- 为什么只支持 rollback latest？
  最小可用闭环：先支持最近一次回退，再逐步扩展。
  复杂的多版本回滚会增加实现和测试成本，当前阶段不值得。

- 为什么区分 created 和 modified？
  rollback 逻辑不同：created 需要删除文件，modified 需要恢复内容。
  history 记录需要准确反映操作类型。

- 为什么用 JSON Lines 而不是 SQLite？
  简单、可读、无额外依赖。
  每行一条记录，方便 grep 和调试。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Literal


# ============================================================
# 数据结构
# ============================================================


@dataclass
class EditHistoryRecord:
    """编辑历史记录

    Attributes:
        record_id: 唯一记录 ID
        timestamp: 操作时间戳（Unix timestamp）
        tool_name: 工具名称（write/edit）
        file_path: 文件绝对路径
        action: 操作类型（created/modified）
        backup_path: 备份文件路径（created 时为 None）
        before_hash: 修改前内容的 SHA256（created 时为空字符串）
        after_hash: 修改后内容的 SHA256
        preview: 操作预览（diff 或内容摘要）
    """
    record_id: str
    timestamp: float
    tool_name: str
    file_path: str
    action: Literal["created", "modified"]
    backup_path: str | None
    before_hash: str
    after_hash: str
    preview: str


# ============================================================
# Store 实现
# ============================================================


class EditHistoryStore:
    """编辑历史持久化存储

    职责:
    - 记录 write/edit 操作历史
    - 管理备份文件
    - 支持 rollback latest

    使用方式:
        store = EditHistoryStore("/workspace/.agent/file-history")
        record = store.record_write(file_path, content, is_new=True)
        latest = store.get_latest()
        store.rollback_latest()
    """

    def __init__(self, history_dir: str) -> None:
        """初始化历史存储

        Args:
            history_dir: 历史记录目录（如 workspace/.agent/file-history）
        """
        self._history_dir = history_dir
        self._backups_dir = os.path.join(history_dir, "backups")
        self._records_file = os.path.join(history_dir, "history.jsonl")

        # 确保目录存在
        os.makedirs(self._history_dir, exist_ok=True)
        os.makedirs(self._backups_dir, exist_ok=True)

    @property
    def history_dir(self) -> str:
        """历史记录目录"""
        return self._history_dir

    @property
    def backups_dir(self) -> str:
        """备份文件目录"""
        return self._backups_dir

    # ========== 记录操作 ==========

    def record_write(
        self,
        file_path: str,
        content: str,
        is_new: bool,
        preview: str = "",
    ) -> EditHistoryRecord:
        """记录 write 操作

        Args:
            file_path: 文件绝对路径
            content: 写入的内容
            is_new: 是否是新建文件
            preview: 操作预览（可选）

        Returns:
            EditHistoryRecord: 创建的历史记录
        """
        action = "created" if is_new else "modified"
        after_hash = self._compute_hash(content)

        # 如果是修改已有文件，创建 backup
        backup_path = None
        before_hash = ""
        if not is_new and os.path.exists(file_path):
            backup_path = self._create_backup(file_path)
            with open(file_path, encoding="utf-8") as f:
                before_hash = self._compute_hash(f.read())

        record = EditHistoryRecord(
            record_id=str(uuid.uuid4()),
            timestamp=time.time(),
            tool_name="write",
            file_path=os.path.abspath(file_path),
            action=action,
            backup_path=backup_path,
            before_hash=before_hash,
            after_hash=after_hash,
            preview=preview,
        )

        self._append_record(record)
        return record

    def record_edit(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        diff_preview: str = "",
    ) -> EditHistoryRecord:
        """记录 edit 操作

        Args:
            file_path: 文件绝对路径
            old_content: 修改前的内容
            new_content: 修改后的内容
            diff_preview: diff 预览

        Returns:
            EditHistoryRecord: 创建的历史记录
        """
        backup_path = self._create_backup(file_path)
        before_hash = self._compute_hash(old_content)
        after_hash = self._compute_hash(new_content)

        record = EditHistoryRecord(
            record_id=str(uuid.uuid4()),
            timestamp=time.time(),
            tool_name="edit",
            file_path=os.path.abspath(file_path),
            action="modified",
            backup_path=backup_path,
            before_hash=before_hash,
            after_hash=after_hash,
            preview=diff_preview,
        )

        self._append_record(record)
        return record

    def record_rollback(
        self,
        file_path: str,
        action: Literal["restored", "deleted"],
        preview: str = "",
    ) -> EditHistoryRecord:
        """记录 rollback 操作

        Args:
            file_path: 文件绝对路径
            action: rollback 动作（restored/deleted）
            preview: 操作预览

        Returns:
            EditHistoryRecord: 创建的历史记录
        """
        record = EditHistoryRecord(
            record_id=str(uuid.uuid4()),
            timestamp=time.time(),
            tool_name="rollback",
            file_path=os.path.abspath(file_path),
            action=action,  # type: ignore[arg-type]
            backup_path=None,
            before_hash="",
            after_hash="",
            preview=preview,
        )

        self._append_record(record)
        return record

    # ========== 查询操作 ==========

    def get_latest(self) -> EditHistoryRecord | None:
        """获取最近一条 write/edit 记录（不含 rollback）

        Returns:
            EditHistoryRecord 或 None（没有记录）
        """
        records = self._load_records()
        # 从后向前找第一条 write/edit 记录
        for record in reversed(records):
            if record.tool_name in ("write", "edit"):
                return record
        return None

    def get_all(self) -> list[EditHistoryRecord]:
        """获取所有历史记录

        Returns:
            历史记录列表（按时间顺序）
        """
        return self._load_records()

    def get_by_file(self, file_path: str) -> list[EditHistoryRecord]:
        """获取指定文件的历史记录

        Args:
            file_path: 文件路径（绝对或相对）

        Returns:
            该文件的历史记录列表
        """
        abs_path = os.path.abspath(file_path)
        return [r for r in self._load_records() if r.file_path == abs_path]

    # ========== Rollback 操作 ==========

    def rollback_latest(self) -> tuple[bool, str]:
        """回退最近一次成功修改

        Returns:
            (success, message): 是否成功，以及操作结果描述
        """
        latest = self.get_latest()
        if latest is None:
            return False, "没有可回退的历史记录"

        if latest.action == "created":
            # 新建文件：删除该文件
            return self._rollback_created(latest)
        elif latest.action == "modified":
            # 修改文件：恢复备份
            return self._rollback_modified(latest)
        else:
            return False, f"不支持的操作类型: {latest.action}"

    def _rollback_created(self, record: EditHistoryRecord) -> tuple[bool, str]:
        """回退新建操作（删除文件）

        Args:
            record: 原始创建记录

        Returns:
            (success, message)
        """
        file_path = record.file_path

        if not os.path.exists(file_path):
            # 文件已经不存在，也算成功
            self.record_rollback(file_path, "deleted", "文件已不存在，无需删除")
            return True, f"文件已不存在: {file_path}"

        try:
            os.remove(file_path)
            self.record_rollback(file_path, "deleted", f"已删除新建的文件: {file_path}")
            return True, f"已回退：删除了新建的文件 {file_path}"
        except OSError as e:
            return False, f"删除文件失败: {e}"

    def _rollback_modified(self, record: EditHistoryRecord) -> tuple[bool, str]:
        """回退修改操作（恢复备份）

        Args:
            record: 原始修改记录

        Returns:
            (success, message)
        """
        if record.backup_path is None:
            return False, "没有备份文件，无法回退"

        if not os.path.exists(record.backup_path):
            return False, f"备份文件不存在: {record.backup_path}"

        try:
            # 读取备份内容
            with open(record.backup_path, encoding="utf-8") as f:
                backup_content = f.read()

            # 恢复到原文件
            with open(record.file_path, "w", encoding="utf-8") as f:
                f.write(backup_content)

            self.record_rollback(
                record.file_path,
                "restored",
                f"已从备份恢复: {record.backup_path}",
            )
            return True, f"已回退：从备份恢复了 {record.file_path}"
        except OSError as e:
            return False, f"恢复文件失败: {e}"

    # ========== 内部方法 ==========

    def _create_backup(self, file_path: str) -> str:
        """创建文件备份

        Args:
            file_path: 要备份的文件路径

        Returns:
            备份文件路径
        """
        abs_path = os.path.abspath(file_path)
        file_name = os.path.basename(abs_path)
        timestamp = int(time.time() * 1000)
        backup_name = f"{file_name}.{timestamp}.bak"
        backup_path = os.path.join(self._backups_dir, backup_name)

        # 复制文件内容
        with open(abs_path, encoding="utf-8") as src:
            content = src.read()
        with open(backup_path, "w", encoding="utf-8") as dst:
            dst.write(content)

        return backup_path

    def _append_record(self, record: EditHistoryRecord) -> None:
        """追加记录到 history 文件

        Args:
            record: 要追加的记录
        """
        with open(self._records_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def _load_records(self) -> list[EditHistoryRecord]:
        """加载所有历史记录

        Returns:
            历史记录列表
        """
        if not os.path.exists(self._records_file):
            return []

        records = []
        with open(self._records_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    records.append(EditHistoryRecord(**data))
                except (json.JSONDecodeError, TypeError):
                    # 跳过损坏的记录
                    continue

        return records

    def _compute_hash(self, content: str) -> str:
        """计算内容的 SHA256 哈希

        Args:
            content: 文件内容

        Returns:
            SHA256 哈希字符串
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
