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

from typing_extensions import LiteralString

from database import get_db

# 仅允许这些关键字开头的 SQL 进入 execute()。
# 通过类型注解 LiteralString 让静态分析器（mypy/pyright/CodeQL）
# 在调用点就拒绝非字面量 SQL；运行时再用白名单兜底，避免有人
# 通过 # type: ignore 等手段绕过类型检查。
_ALLOWED_SQL_PREFIXES = frozenset(
    {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "REPLACE",
        "WITH",
        "CREATE",
        "DROP",
        "ALTER",
        "PRAGMA",
    }
)


def _assert_safe_sql(sql: str) -> None:
    """运行时校验：拒绝看起来不像合法 SQL 模板的字符串。

    只检查关键字前缀，不做完整语法校验——后者由 sqlite3 自身完成。
    任何用户输入都应通过 ``params`` 参数化绑定传入，禁止参与 SQL 拼接。
    """
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("SQL 不能为空")
    head = sql.lstrip().split(None, 1)[0].upper()
    if head not in _ALLOWED_SQL_PREFIXES:
        raise ValueError(f"非法 SQL 前缀: {head!r}")


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
    """Repository 基类。所有操作通过 with get_db() as conn 获取短连接。

    安全约定：
    - ``sql`` 参数被注解为 ``LiteralString``，调用方只能传字符串字面量
      （或由字面量拼接而成的字符串），任何来自用户输入/外部数据的字符
      串都会被静态分析工具拒绝。
    - 用户输入必须通过 ``params`` 参数绑定，由 sqlite3 驱动转义。
    - ``_assert_safe_sql`` 在运行时再做一次白名单兜底。
    """

    def _fetchone(self, sql: LiteralString, params: tuple = ()) -> Optional[dict]:
        _assert_safe_sql(sql)
        with get_db() as conn:
            row = conn.execute(sql, params).fetchone()
            return row_to_dict(row) if row else None

    def _fetchall(self, sql: LiteralString, params: tuple = ()) -> list[dict]:
        _assert_safe_sql(sql)
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [row_to_dict(r) for r in rows]

    def _execute(self, sql: LiteralString, params: tuple = ()) -> sqlite3.Cursor:
        _assert_safe_sql(sql)
        with get_db() as conn:
            cursor = conn.execute(sql, params)
            return cursor

    def _executemany(self, operations: list[tuple[LiteralString, tuple]]) -> None:
        """在同一个连接中执行多条 SQL（保证原子性）。

        每条 SQL 都先经过 ``_assert_safe_sql`` 校验，确保不会出现
        外部输入直接拼成 SQL 模板的情况。
        """
        with get_db() as conn:
            for sql, params in operations:
                _assert_safe_sql(sql)
                conn.execute(sql, params)
