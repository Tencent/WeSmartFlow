"""
SessionRepository：会话数据访问层

消息存储在独立 JSON 文件（data/sessions/{id}.json），
此 repo 只管理会话元数据（SQLite）+ 消息文件读写。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from config import SESSIONS_DIR
from models.session import (
    SessionSchema,
    SessionDetail,
    MessageSchema,
    SessionCreate,
    SessionFile,
)
from .base import BaseRepository, _loads, _dumps, new_id, utcnow_str


def _row_to_schema(row: dict) -> SessionSchema:
    return SessionSchema(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        topic=row.get("topic"),
        status=row["status"],
        node_ids_covered=_loads(row["node_ids_covered"], []),
        files=_loads(row["files"], []),
        message_count=row["message_count"],
        duration_minutes=row["duration_minutes"],
        created_at=row["created_at"],
        ended_at=row["ended_at"],
    )


class SessionRepository(BaseRepository):
    def get_all(self, user_id: str, limit: int = 20) -> list[SessionSchema]:
        rows = self._fetchall(
            "SELECT * FROM sessions WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [_row_to_schema(r) for r in rows]

    def get_by_id(self, session_id: str) -> Optional[SessionSchema]:
        row = self._fetchone("SELECT * FROM sessions WHERE id=?", (session_id,))
        return _row_to_schema(row) if row else None

    def get_detail(self, session_id: str) -> Optional[SessionDetail]:
        session = self.get_by_id(session_id)
        if not session:
            return None
        messages = self._read_messages(session_id)
        return SessionDetail(**session.model_dump(), messages=messages)

    def create(self, user_id: str, data: SessionCreate) -> SessionSchema:
        session_id = new_id()
        now = utcnow_str()

        self._execute(
            """
            INSERT INTO sessions
              (id, user_id, title, topic, status, node_ids_covered,
               files, message_count, duration_minutes, created_at, ended_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                session_id,
                user_id,
                None,
                data.topic,
                "active",
                _dumps(data.node_ids),
                _dumps([]),
                0,
                0,
                now,
                None,
            ),
        )
        # 初始化空消息文件
        self._messages_path(session_id).write_text("[]", encoding="utf-8")
        return self.get_by_id(session_id)

    def append_message(self, session_id: str, message: MessageSchema) -> None:
        """追加一条消息到消息文件，并更新 message_count"""
        messages = self._read_messages(session_id)
        messages.append(message.model_dump(mode="json"))

        self._messages_path(session_id).write_text(
            json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._execute(
            "UPDATE sessions SET message_count=? WHERE id=?",
            (len(messages), session_id),
        )

    def update_nodes_covered(self, session_id: str, node_ids: list[str]) -> None:
        self._execute(
            "UPDATE sessions SET node_ids_covered=? WHERE id=?",
            (_dumps(node_ids), session_id),
        )

    def append_session_file(self, session_id: str, file: SessionFile) -> None:
        """向会话的 files 列表追加一条文件记录"""
        row = self._fetchone("SELECT files FROM sessions WHERE id=?", (session_id,))
        if not row:
            return
        files: list[dict] = _loads(row["files"], [])
        files.append(file.model_dump(mode="json"))
        self._execute(
            "UPDATE sessions SET files=? WHERE id=?", (_dumps(files), session_id)
        )

    def add_duration(self, session_id: str, minutes: int) -> None:
        """累加会话时长（不改变 status）"""
        self._execute(
            "UPDATE sessions SET duration_minutes=duration_minutes+? WHERE id=?",
            (minutes, session_id),
        )

    def set_title(self, session_id: str, title: str) -> None:
        self._execute("UPDATE sessions SET title=? WHERE id=?", (title, session_id))

    def complete(
        self,
        session_id: str,
        duration_minutes: int,
        node_ids: list[str],
        files: list[dict],
    ) -> None:
        """收尾会话：标记 completed，并写入 duration / node_ids_covered / files / ended_at。"""
        now = utcnow_str()
        self._execute(
            """
            UPDATE sessions
               SET status='completed',
                   duration_minutes=?,
                   node_ids_covered=?,
                   files=?,
                   ended_at=?
             WHERE id=?
            """,
            (
                duration_minutes,
                _dumps(node_ids),
                _dumps(files),
                now,
                session_id,
            ),
        )

    @staticmethod
    def _messages_path(session_id: str) -> Path:
        """根据 session_id 直接构造消息文件的绝对路径"""
        return SESSIONS_DIR / f"{session_id}.json"

    def _read_messages(self, session_id: str) -> list[dict]:
        path = self._messages_path(session_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
