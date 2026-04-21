"""
Repository 基类：通用 CRUD 工具方法
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _dumps(obj: Any) -> str:
    """序列化为 JSON 字符串（存入 SQLite JSON 列）"""
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False)


def _loads(s: Optional[str], default=None):
    """从 SQLite JSON 列反序列化"""
    if s is None:
        return default
    if isinstance(s, (list, dict)):
        return s
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return default


class BaseRepository:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def _fetchone(self, sql: str, params: tuple = ()) -> Optional[dict]:
        row = self.db.execute(sql, params).fetchone()
        return row_to_dict(row) if row else None

    def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        rows = self.db.execute(sql, params).fetchall()
        return [row_to_dict(r) for r in rows]

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.db.execute(sql, params)

    def commit(self) -> None:
        """提交当前事务"""
        self.db.commit()
