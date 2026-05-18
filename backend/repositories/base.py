"""
Repository 基类：通用 CRUD 工具方法

统一连接管理策略：
- 所有数据库操作通过 `with get_db() as conn` 获取短连接
- 每次操作独立获取连接，执行完毕自动 commit 并关闭
- 不再通过构造函数注入 db 连接，彻底消除长连接占用问题
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from database import get_db


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
    """Repository 基类。所有操作通过 with get_db() as conn 获取短连接。"""

    def _fetchone(self, sql: str, params: tuple = ()) -> Optional[dict]:
        with get_db() as conn:
            row = conn.execute(sql, params).fetchone()
            return row_to_dict(row) if row else None

    def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [row_to_dict(r) for r in rows]

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with get_db() as conn:
            cursor = conn.execute(sql, params)
            return cursor

    def _executemany(self, operations: list[tuple[str, tuple]]) -> None:
        """在同一个连接中执行多条 SQL（保证原子性）。"""
        with get_db() as conn:
            for sql, params in operations:
                conn.execute(sql, params)
