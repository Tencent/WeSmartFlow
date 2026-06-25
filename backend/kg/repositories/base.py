"""
KG Repository 工具方法
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ..database import get_kg_db


def new_id() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------
# 稳定 id 派生（OKF 通路使用）
#
# 设计原则:
#   - id 完全由"业务身份字段"派生, 同一身份永远算出同一 id, 天然支持幂等 upsert
#   - 不引入 hash, 直接路径化, 调试 / 日志 / SQL LIKE 查询都极度友好
#   - 飞轮通路 (origin != 'okf') 仍走 new_id() 生成 UUID, 与本路径共存无冲突
#
# 命名约定:
#   concept_id : "{subject}/{slug}"                       e.g. "math/derivative"
#   facet_id   : "{concept_id}/{kind}"                    e.g. "math/derivative/直观理解"
#   edge_id    : "{src_id}||{relation_type}||{dst_id}"    e.g. "math/derivative||prerequisite||math/limit"
#
# 用 '||' 而非 '/' 作为 edge id 的分隔符, 是为了避免与 cid 内部的 '/' 冲突,
# 让 edge id 始终能用 ".split('||')" 还原回 (src, rel, dst) 三元组。
#
# ingester 必须在解析阶段强制以下字符约束 (违反则报错跳过整个文件):
#   - subject / slug / kind 都不允许出现 '/'
#   - src_id / dst_id 内部不允许出现 '||' (cid 派生规则已天然保证)
# --------------------------------------------------------------------------

_FORBIDDEN_IN_PATH = "/"
_EDGE_SEP = "||"


def _check_path_segment(value: str, *, field_name: str) -> str:
    """校验单个路径片段不含禁用字符, 失败抛 ValueError。"""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} 不能为空")
    if _FORBIDDEN_IN_PATH in value:
        raise ValueError(
            f"{field_name}={value!r} 含有禁用字符 '/', 无法用作稳定 id 的路径片段"
        )
    return value


def derive_concept_id(subject: str, slug: str) -> str:
    """concept 的稳定身份 id: ``"{subject}/{slug}"``。

    例: ``derive_concept_id("math", "derivative") == "math/derivative"``。

    Raises:
        ValueError: subject 或 slug 含 '/', 或为空。
    """
    _check_path_segment(subject, field_name="subject")
    _check_path_segment(slug, field_name="slug")
    return f"{subject}/{slug}"


def derive_facet_id(concept_id: str, kind: str) -> str:
    """facet 的稳定身份 id: ``"{concept_id}/{kind}"``。

    例: ``derive_facet_id("math/derivative", "直观理解") == "math/derivative/直观理解"``。

    语义: 同 concept 下同 H1 标题 (kind) 视为同一条 facet。
    内容修改走 update; 标题改了则会被视为"新 facet 上线 + 旧 facet 下线"。

    Raises:
        ValueError: concept_id 为空, 或 kind 为空 / 含 '/'。
    """
    if not isinstance(concept_id, str) or not concept_id:
        raise ValueError("concept_id 不能为空")
    _check_path_segment(kind, field_name="kind")
    return f"{concept_id}/{kind}"


def derive_edge_id(src_id: str, dst_id: str, relation_type: str) -> str:
    """edge 的稳定身份 id: ``"{src_id}||{relation_type}||{dst_id}"``。

    例: ``derive_edge_id("math/derivative", "math/limit", "prerequisite")
         == "math/derivative||prerequisite||math/limit"``。

    Raises:
        ValueError: 任何一段为空, 或包含分隔符 '||'。
    """
    for name, value in (
        ("src_id", src_id),
        ("dst_id", dst_id),
        ("relation_type", relation_type),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} 不能为空")
        if _EDGE_SEP in value:
            raise ValueError(
                f"{name}={value!r} 含有禁用分隔符 '||', 无法用作 edge id 片段"
            )
    return f"{src_id}{_EDGE_SEP}{relation_type}{_EDGE_SEP}{dst_id}"


def utcnow_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def dumps(obj: Any) -> str:
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False)


def loads(s: Optional[str], default=None):
    if s is None or s == "":
        return default
    if isinstance(s, (list, dict)):
        return s
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return default


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class KGBaseRepo:
    """KG Repository 基类。"""

    def _fetchone(self, sql: str, params: tuple = ()) -> Optional[dict]:
        with get_kg_db() as conn:
            row = conn.execute(sql, params).fetchone()
            return row_to_dict(row) if row else None

    def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        with get_kg_db() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [row_to_dict(r) for r in rows]

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with get_kg_db() as conn:
            return conn.execute(sql, params)

    def _txn(self, ops: list[tuple[str, tuple]]) -> None:
        """同一连接内执行多条 SQL，保证原子性。"""
        with get_kg_db() as conn:
            for sql, params in ops:
                conn.execute(sql, params)
