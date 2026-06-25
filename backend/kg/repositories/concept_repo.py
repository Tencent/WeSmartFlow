"""
ConceptRepository：概念节点数据访问层
"""

from __future__ import annotations

from typing import Optional

from ..database import get_kg_db
from ..models import (
    ConceptAlias,
    ConceptBrief,
    ConceptCreate,
    ConceptResolveItem,
    ConceptSchema,
    ConceptUpdate,
)
from ..text_for_embedding import build_concept_text
from ..vector_store import COLLECTION_CONCEPT, get_vector_store
from .base import KGBaseRepo, dumps, loads, new_id, utcnow_str


def _row_to_schema(row: dict) -> ConceptSchema:
    return ConceptSchema(
        id=row["id"],
        slug=row["slug"],
        canonical_name=row["canonical_name"],
        aliases=[ConceptAlias(**a) for a in loads(row["aliases"], [])],
        summary=row["summary"] or "",
        subject=row["subject"] or "",
        difficulty=row["difficulty"],
        status=row["status"],
        tags=loads(row["tags"], []),
        merged_into_id=row["merged_into_id"],
        embedding_model=row["embedding_model"] or "",
        vector_id=row["vector_id"] or "",
        source_hash=(row["source_hash"] if "source_hash" in row.keys() else "") or "",
        created_by=row["created_by"] or "",
        updated_by=row["updated_by"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_brief(row: dict) -> ConceptBrief:
    return ConceptBrief(
        id=row["id"],
        slug=row["slug"],
        canonical_name=row["canonical_name"],
        summary=row["summary"] or "",
        subject=row["subject"] or "",
        difficulty=row["difficulty"],
    )


class ConceptRepository(KGBaseRepo):
    # ---------- 写 ----------

    def create(self, data: ConceptCreate) -> ConceptSchema:
        # 调用方派生过稳定 id (OKF 通路) 就用它; 否则回退 UUID (飞轮通路)。
        cid = data.id or new_id()
        now = utcnow_str()
        aliases_dump = [a.model_dump() for a in data.aliases]
        aliases_json = dumps(aliases_dump)

        # 先写 SQLite
        with get_kg_db() as conn:
            conn.execute(
                """
                INSERT INTO concept
                  (id, slug, canonical_name, aliases, summary, subject,
                   difficulty, status, tags, embedding_model, vector_id,
                   source_hash, created_by, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    cid,
                    data.slug,
                    data.canonical_name,
                    aliases_json,
                    data.summary,
                    data.subject,
                    data.difficulty,
                    data.status,
                    dumps(data.tags),
                    "",
                    "",
                    data.source_hash or "",
                    data.created_by,
                    now,
                    now,
                ),
            )
            conn.commit()

        # 再同步向量；严格模式下失败回滚 SQLite。
        from ..config import KG_STRICT_VECTOR_WRITE

        try:
            emb_text = build_concept_text(
                {
                    "canonical_name": data.canonical_name,
                    "aliases": aliases_dump,
                    "summary": data.summary,
                    "subject": data.subject,
                    "tags": data.tags,
                }
            )
            vid, model = get_vector_store().upsert(
                COLLECTION_CONCEPT,
                biz_id=cid,
                text=emb_text,
                payload={
                    "concept_id": cid,
                    "slug": data.slug,
                    "subject": data.subject,
                },
            )
            if vid:
                with get_kg_db() as conn:
                    conn.execute(
                        "UPDATE concept SET embedding_model=?, vector_id=? WHERE id=?",
                        (model, vid, cid),
                    )
                    conn.commit()
            elif KG_STRICT_VECTOR_WRITE:
                self._rollback_concept(cid, reason="upsert 返回空 vid")
                raise RuntimeError(f"严格双写: concept={cid} 向量同步失败")
        except RuntimeError:
            raise
        except Exception:
            self._rollback_concept(cid, reason="upsert 异常")
            raise

        return self.get_by_id(cid)

    def _rollback_concept(self, cid: str, reason: str) -> None:
        import logging

        log = logging.getLogger(__name__)
        log.warning("concept 写入回滚 cid=%s reason=%s", cid, reason)
        try:
            with get_kg_db() as conn:
                conn.execute("DELETE FROM concept WHERE id=?", (cid,))
                conn.commit()
        except Exception:  # pylint: disable=broad-except
            log.exception("concept 回滚失败 cid=%s, 可能产生脏数据", cid)

    def update(self, concept_id: str, data: ConceptUpdate) -> Optional[ConceptSchema]:
        fields, values = [], []
        if data.canonical_name is not None:
            fields.append("canonical_name=?")
            values.append(data.canonical_name)
        if data.aliases is not None:
            fields.append("aliases=?")
            values.append(dumps([a.model_dump() for a in data.aliases]))
        if data.summary is not None:
            fields.append("summary=?")
            values.append(data.summary)
        if data.subject is not None:
            fields.append("subject=?")
            values.append(data.subject)
        if data.difficulty is not None:
            fields.append("difficulty=?")
            values.append(data.difficulty)
        if data.status is not None:
            fields.append("status=?")
            values.append(data.status)
        if data.tags is not None:
            fields.append("tags=?")
            values.append(dumps(data.tags))
        if data.source_hash is not None:
            fields.append("source_hash=?")
            values.append(data.source_hash)
        if data.updated_by is not None:
            fields.append("updated_by=?")
            values.append(data.updated_by)

        if not fields:
            return self.get_by_id(concept_id)

        fields.append("updated_at=?")
        values.append(utcnow_str())
        values.append(concept_id)

        with get_kg_db() as conn:
            conn.execute(
                f"UPDATE concept SET {', '.join(fields)} WHERE id=?", tuple(values)
            )
            row = conn.execute(
                "SELECT canonical_name, aliases, summary, slug, subject, tags FROM concept WHERE id=?",
                (concept_id,),
            ).fetchone()
            conn.commit()

        # 同步向量
        if row:
            aliases = loads(row["aliases"], [])
            tags = loads(row["tags"], [])
            emb_text = build_concept_text(
                {
                    "canonical_name": row["canonical_name"],
                    "aliases": aliases,
                    "summary": row["summary"] or "",
                    "subject": row["subject"] or "",
                    "tags": tags,
                }
            )
            vid, model = get_vector_store().upsert(
                COLLECTION_CONCEPT,
                biz_id=concept_id,
                text=emb_text,
                payload={
                    "concept_id": concept_id,
                    "slug": row["slug"],
                    "subject": row["subject"] or "",
                },
            )
            if vid:
                with get_kg_db() as conn:
                    conn.execute(
                        "UPDATE concept SET embedding_model=?, vector_id=? WHERE id=?",
                        (model, vid, concept_id),
                    )
                    conn.commit()

        return self.get_by_id(concept_id)

    def delete(self, concept_id: str) -> bool:
        with get_kg_db() as conn:
            cur = conn.execute("DELETE FROM concept WHERE id=?", (concept_id,))
            conn.commit()
            ok = cur.rowcount > 0
        if ok:
            get_vector_store().delete(COLLECTION_CONCEPT, concept_id)
        return ok

    # ---------- 增量同步专用 ----------

    def upsert(self, data: ConceptCreate) -> tuple[ConceptSchema, str]:
        """OKF 增量同步专用：按派生 id 写入或更新。

        语义：
          - 不存在 → 等价 self.create(data)，action='created'
          - 已存在且 source_hash 与传入相同 → 完全跳过，action='unchanged'
          - 已存在且 hash 不同 → 把 canonical_name/aliases/summary/subject/
            difficulty/status/tags/source_hash 全量覆盖；若任一影响 embedding 的
            字段实际变了，重新刷一次向量。action='updated'

        约定：
          调用方必须传 data.id（OKF 通路用 derive_concept_id 派生）。
          为保留"飞轮通路 UUID 兜底"的纯净性，本方法不允许 id 为空。
        """
        if not data.id:
            raise ValueError("upsert 必须传入 data.id（派生 id）")

        existing = self.get_by_id(data.id)
        if existing is None:
            return self.create(data), "created"

        # 已存在：source_hash 没变 → 全文件跳过
        if data.source_hash and existing.source_hash == data.source_hash:
            return existing, "unchanged"

        # source_hash 变了 → 真正 update
        new_aliases_dump = [a.model_dump() for a in data.aliases]

        # 检测影响 embedding 的字段是否变化（决定是否重刷向量）
        embedding_dirty = (
            existing.canonical_name != data.canonical_name
            or [a.model_dump() for a in existing.aliases] != new_aliases_dump
            or (existing.summary or "") != (data.summary or "")
            or (existing.subject or "") != (data.subject or "")
            or sorted(existing.tags) != sorted(data.tags)
        )

        now = utcnow_str()
        with get_kg_db() as conn:
            conn.execute(
                """
                UPDATE concept
                   SET canonical_name=?, aliases=?, summary=?, subject=?,
                       difficulty=?, status=?, tags=?, source_hash=?,
                       updated_by=?, updated_at=?
                 WHERE id=?
                """,
                (
                    data.canonical_name,
                    dumps(new_aliases_dump),
                    data.summary,
                    data.subject,
                    data.difficulty,
                    data.status,
                    dumps(data.tags),
                    data.source_hash or "",
                    data.created_by,
                    now,
                    data.id,
                ),
            )
            conn.commit()

        # 仅在影响 embedding 的字段变化时才重刷向量（节省 API）
        if embedding_dirty:
            emb_text = build_concept_text(
                {
                    "canonical_name": data.canonical_name,
                    "aliases": new_aliases_dump,
                    "summary": data.summary,
                    "subject": data.subject,
                    "tags": data.tags,
                }
            )
            vid, model = get_vector_store().upsert(
                COLLECTION_CONCEPT,
                biz_id=data.id,
                text=emb_text,
                payload={
                    "concept_id": data.id,
                    "slug": data.slug,
                    "subject": data.subject,
                },
            )
            if vid:
                with get_kg_db() as conn:
                    conn.execute(
                        "UPDATE concept SET embedding_model=?, vector_id=? WHERE id=?",
                        (model, vid, data.id),
                    )
                    conn.commit()

        updated = self.get_by_id(data.id)
        assert updated is not None
        return updated, "updated"

    def merge(
        self, from_id: str, into_id: str, reason: str = "", operator_id: str = ""
    ) -> bool:
        """把 from 概念合并到 into，设置 merged_into_id。"""
        if from_id == into_id:
            return False
        now = utcnow_str()
        with get_kg_db() as conn:
            target = conn.execute(
                "SELECT id FROM concept WHERE id=?", (into_id,)
            ).fetchone()
            src = conn.execute(
                "SELECT id FROM concept WHERE id=?", (from_id,)
            ).fetchone()
            if not target or not src:
                return False
            conn.execute(
                "UPDATE concept SET merged_into_id=?, status='deprecated', updated_at=? WHERE id=?",
                (into_id, now, from_id),
            )
            conn.commit()
        # 合并后从向量库删除已废弃的 from 概念
        get_vector_store().delete(COLLECTION_CONCEPT, from_id)
        return True

    # ---------- 读 ----------

    def get_by_id(self, concept_id: str) -> Optional[ConceptSchema]:
        row = self._fetchone("SELECT * FROM concept WHERE id=?", (concept_id,))
        return _row_to_schema(row) if row else None

    def get_by_slug(self, slug: str) -> Optional[ConceptSchema]:
        row = self._fetchone("SELECT * FROM concept WHERE slug=?", (slug,))
        return _row_to_schema(row) if row else None

    def follow_merge(self, concept_id: str) -> Optional[ConceptSchema]:
        """跟随 merged_into_id 跳转到当前生效概念。"""
        seen = set()
        current = self.get_by_id(concept_id)
        while current and current.merged_into_id and current.id not in seen:
            seen.add(current.id)
            nxt = self.get_by_id(current.merged_into_id)
            if not nxt:
                break
            current = nxt
        return current

    def list_briefs(
        self,
        subject: Optional[str] = None,
        status: Optional[str] = "approved",
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConceptBrief]:
        sql = "SELECT * FROM concept WHERE 1=1"
        params: list = []
        if subject:
            sql += " AND subject=?"
            params.append(subject)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._fetchall(sql, tuple(params))
        return [_row_to_brief(r) for r in rows]

    # ---------- 实体链接 ----------

    def resolve(self, term: str, top_k: int = 1) -> list[ConceptResolveItem]:
        """实体链接：精确名 → 别名 → 向量 → FTS。"""
        if not term or not term.strip():
            return []
        term = term.strip()

        # 1) 精确 canonical_name 命中
        rows = self._fetchall(
            "SELECT id, slug, canonical_name FROM concept "
            "WHERE canonical_name=? AND status='approved' LIMIT 1",
            (term,),
        )
        if rows:
            r = rows[0]
            return [
                ConceptResolveItem(
                    term=term,
                    concept_id=r["id"],
                    slug=r["slug"],
                    canonical_name=r["canonical_name"],
                    score=1.0,
                    match_type="exact",
                )
            ]

        # 2) 别名命中
        rows = self._fetchall(
            "SELECT id, slug, canonical_name, aliases FROM concept "
            "WHERE aliases LIKE ? AND status='approved' LIMIT 5",
            (f'%"name": "{term}"%',),
        )
        results: list[ConceptResolveItem] = []
        for r in rows:
            aliases = loads(r["aliases"], [])
            if any(a.get("name") == term for a in aliases):
                results.append(
                    ConceptResolveItem(
                        term=term,
                        concept_id=r["id"],
                        slug=r["slug"],
                        canonical_name=r["canonical_name"],
                        score=0.9,
                        match_type="alias",
                    )
                )
        if results:
            return results[:top_k]

        # 3) 向量召回（如果启用）
        store = get_vector_store()
        if store.enabled:
            hits = store.search(COLLECTION_CONCEPT, term, top_k=top_k)
            for h in hits:
                # 阈值：cosine 相似度 < 0.5 视为不可信，丢弃
                if h["score"] < 0.5:
                    continue
                cid = h["payload"].get("concept_id") or h["biz_id"]
                if not cid:
                    continue
                c = self.get_by_id(cid)
                if not c or c.status != "approved":
                    continue
                results.append(
                    ConceptResolveItem(
                        term=term,
                        concept_id=c.id,
                        slug=c.slug,
                        canonical_name=c.canonical_name,
                        score=float(h["score"]),
                        match_type="vector",
                    )
                )
            if results:
                return results[:top_k]

        return (
            results[:top_k]
            if results
            else [ConceptResolveItem(term=term, score=0.0, match_type="none")]
        )

    def exists_any_approved(self) -> bool:
        """KG 中是否存在任意 approved concept。用于 retrieve 区分"空库"vs"查偏"。

        SELECT 1 + LIMIT 1 的极轻量探测,O(1) 索引命中。
        """
        row = self._fetchone("SELECT 1 FROM concept WHERE status='approved' LIMIT 1")
        return bool(row)
