"""
FacetRepository：切面（教法 + 共性反馈）数据访问层

切面是挂在 concept 下、可独立检索的内容单元。
- 同一 (concept_id, kind) 可以有多条 facet（用 list 而非 dict）
- 通过 layer 区分 pedagogy / feedback
- 内置 support_count 用于沉淀"被反复印证"的内容
"""

from __future__ import annotations

from typing import Any, Optional

from ..database import get_kg_db
from ..models import (
    FacetBrief,
    FacetCreate,
    FacetSchema,
    FacetUpdate,
)
from ..text_for_embedding import build_facet_text
from ..vector_store import COLLECTION_FACET, get_vector_store
from .base import KGBaseRepo, dumps, loads, new_id, utcnow_str


def _row_to_schema(row: dict) -> FacetSchema:
    return FacetSchema(
        id=row["id"],
        concept_id=row["concept_id"],
        kind=row["kind"],
        content=row["content"] or "",
        extra=loads(row["extra"], {}),
        status=row["status"],
        confidence=row["confidence"],
        support_count=row["support_count"],
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        origin=row["origin"],
        origin_ref=loads(row["origin_ref"], {}),
        embedding_model=row["embedding_model"] or "",
        vector_id=row["vector_id"] or "",
        created_by=row["created_by"] or "",
        updated_by=row["updated_by"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_brief(row: dict, score: float = 0.0) -> FacetBrief:
    return FacetBrief(
        id=row["id"],
        concept_id=row["concept_id"],
        kind=row["kind"],
        content=row["content"] or "",
        confidence=row["confidence"],
        support_count=row["support_count"],
        score=score,
    )


class FacetRepository(KGBaseRepo):
    # ---------- 写 ----------

    def create(self, data: FacetCreate, concept_brief: Any = None) -> FacetSchema:
        # 调用方派生过稳定 id (OKF 通路) 就用它; 否则回退 UUID (飞轮通路)。
        fid = data.id or new_id()
        now = utcnow_str()

        with get_kg_db() as conn:
            conn.execute(
                """
                INSERT INTO facet
                  (id, concept_id, kind, content, extra,
                   status, confidence, support_count, first_seen_at, last_seen_at,
                   origin, origin_ref, embedding_model, vector_id,
                   created_by, updated_by, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    fid,
                    data.concept_id,
                    data.kind,
                    data.content,
                    dumps(data.extra or {}),
                    data.status,
                    max(0.0, min(1.0, float(data.confidence))),
                    0,
                    now,
                    now,
                    data.origin,
                    dumps(data.origin_ref or {}),
                    "",
                    "",
                    data.created_by,
                    data.created_by,
                    now,
                    now,
                ),
            )
            conn.commit()

        # 同步向量（仅 active 的才建索引，避免污染召回池）
        # 双写一致性：严格模式下，向量同步失败/异常都会回滚 SQLite。
        if data.status == "active":
            try:
                vid_ok = self._reindex(fid, concept_brief=concept_brief)
            except Exception as exc:
                self._rollback_facet(fid, reason=f"reindex异常: {exc}")
                raise
            else:
                from ..config import KG_STRICT_VECTOR_WRITE

                if KG_STRICT_VECTOR_WRITE and not vid_ok:
                    self._rollback_facet(fid, reason="reindex 返回空 vid")
                    raise RuntimeError(f"严格双写: facet={fid} 向量同步失败")

        return self.get_by_id(fid)  # type: ignore[return-value]

    def _rollback_facet(self, fid: str, reason: str) -> None:
        """删除刚插入的 facet 行（用于双写失败回滚）。"""
        import logging

        log = logging.getLogger(__name__)
        log.warning("facet 写入回滚 fid=%s reason=%s", fid, reason)
        try:
            with get_kg_db() as conn:
                conn.execute("DELETE FROM facet WHERE id=?", (fid,))
                conn.commit()
        except Exception:  # pylint: disable=broad-except
            log.exception("facet 回滚失败 fid=%s, 可能产生脏数据", fid)

    def update(
        self,
        facet_id: str,
        data: FacetUpdate,
        concept_brief: Any = None,
    ) -> Optional[FacetSchema]:
        fields, values = [], []
        if data.kind is not None:
            fields.append("kind=?")
            values.append(data.kind)
        if data.content is not None:
            fields.append("content=?")
            values.append(data.content)
        if data.extra is not None:
            fields.append("extra=?")
            values.append(dumps(data.extra))
        if data.confidence is not None:
            fields.append("confidence=?")
            values.append(max(0.0, min(1.0, float(data.confidence))))
        if data.status is not None:
            fields.append("status=?")
            values.append(data.status)
        if data.updated_by is not None:
            fields.append("updated_by=?")
            values.append(data.updated_by)

        if not fields:
            return self.get_by_id(facet_id)

        fields.append("updated_at=?")
        values.append(utcnow_str())
        values.append(facet_id)

        with get_kg_db() as conn:
            conn.execute(
                f"UPDATE facet SET {', '.join(fields)} WHERE id=?", tuple(values)
            )
            conn.commit()

        # 内容/状态变了就重建索引；status=archived 直接踢出向量库
        cur = self.get_by_id(facet_id)
        if cur:
            if cur.status == "active":
                self._reindex(facet_id, concept_brief=concept_brief)
            else:
                get_vector_store().delete(COLLECTION_FACET, facet_id)
        return cur

    def archive(self, facet_id: str, updated_by: str = "") -> bool:
        return (
            self.update(facet_id, FacetUpdate(status="archived", updated_by=updated_by))
            is not None
        )

    def increment_support(self, facet_id: str, by: int = 1) -> bool:
        now = utcnow_str()
        with get_kg_db() as conn:
            cur = conn.execute(
                "UPDATE facet SET support_count = support_count + ?, "
                "last_seen_at = ? WHERE id=?",
                (by, now, facet_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete(self, facet_id: str) -> bool:
        with get_kg_db() as conn:
            cur = conn.execute("DELETE FROM facet WHERE id=?", (facet_id,))
            conn.commit()
            ok = cur.rowcount > 0
        if ok:
            get_vector_store().delete(COLLECTION_FACET, facet_id)
        return ok

    # ---------- 增量同步专用 ----------

    def upsert(
        self,
        data: FacetCreate,
        concept_brief: Any = None,
    ) -> tuple[FacetSchema, str]:
        """OKF 增量同步专用：按派生 id 写入或更新。

        语义：
          - 不存在 → 等价 self.create(data, concept_brief)，action='created'
          - 已存在且 content / kind / extra / status / origin_ref 都没变
            → 完全跳过，action='unchanged'
          - 已存在但任一字段变了 → 全量覆盖；只有 content 变了才重刷向量。
            action='updated'

        约定：调用方必须传 data.id（OKF 用 derive_facet_id 派生）。
        """
        if not data.id:
            raise ValueError("upsert 必须传入 data.id（派生 id）")

        existing = self.get_by_id(data.id)
        if existing is None:
            return self.create(data, concept_brief=concept_brief), "created"

        # 比对哪些字段变了
        new_extra = data.extra or {}
        new_origin_ref = data.origin_ref or {}
        content_changed = (existing.content or "") != (data.content or "")
        meta_changed = (
            existing.kind != data.kind
            or (existing.extra or {}) != new_extra
            or existing.status != data.status
            or (existing.origin_ref or {}) != new_origin_ref
            or abs(existing.confidence - float(data.confidence)) > 1e-9
        )
        if not content_changed and not meta_changed:
            return existing, "unchanged"

        now = utcnow_str()
        with get_kg_db() as conn:
            conn.execute(
                """
                UPDATE facet
                   SET kind=?, content=?, extra=?, status=?, confidence=?,
                       origin=?, origin_ref=?, last_seen_at=?, updated_by=?,
                       updated_at=?
                 WHERE id=?
                """,
                (
                    data.kind,
                    data.content,
                    dumps(new_extra),
                    data.status,
                    max(0.0, min(1.0, float(data.confidence))),
                    data.origin,
                    dumps(new_origin_ref),
                    now,
                    data.created_by,
                    now,
                    data.id,
                ),
            )
            conn.commit()

        # 内容变了才重刷向量；仅修改 confidence/status 等元数据无需重 embed
        if data.status == "active" and content_changed:
            try:
                self._reindex(data.id, concept_brief=concept_brief)
            except Exception:  # pylint: disable=broad-except
                import logging

                logging.getLogger(__name__).exception(
                    "facet upsert reindex 失败 fid=%s", data.id
                )
        elif data.status != "active":
            # 状态从 active → archived 时把向量踢出召回池
            get_vector_store().delete(COLLECTION_FACET, data.id)

        updated = self.get_by_id(data.id)
        assert updated is not None
        return updated, "updated"

    # ---------- 读 ----------

    def get_by_id(self, facet_id: str) -> Optional[FacetSchema]:
        row = self._fetchone("SELECT * FROM facet WHERE id=?", (facet_id,))
        return _row_to_schema(row) if row else None

    def list_by_concept(
        self,
        concept_id: str,
        kinds: Optional[list[str]] = None,
        status: str = "active",
        limit: int = 50,
    ) -> list[FacetSchema]:
        clauses = ["concept_id=?"]
        params: list[Any] = [concept_id]
        if status:
            clauses.append("status=?")
            params.append(status)
        if kinds:
            clauses.append(f"kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        sql = (
            "SELECT * FROM facet WHERE "
            + " AND ".join(clauses)
            + " ORDER BY confidence DESC, support_count DESC, updated_at DESC LIMIT ?"
        )
        params.append(limit)
        rows = self._fetchall(sql, tuple(params))
        return [_row_to_schema(r) for r in rows]

    def list_by_concept_and_origin(
        self,
        concept_id: str,
        origin: str = "okf",
    ) -> list[FacetSchema]:
        """列出 concept 下指定 origin 的所有 facet（不限 status，给增量同步算 diff 用）。"""
        rows = self._fetchall(
            "SELECT * FROM facet WHERE concept_id=? AND origin=?",
            (concept_id, origin),
        )
        return [_row_to_schema(r) for r in rows]

    def search(
        self,
        query: str,
        concept_ids: list[str],
        kinds: Optional[list[str]] = None,
        top_k: int = 10,
        per_concept_cap: Optional[int] = None,
    ) -> list[FacetBrief]:
        """子图内 facet 检索：concept 范围限定 + 向量召回 + 按 concept 公平配额。

        必须有 concept_ids 范围（来自 Graph RAG 的子图）；否则返回空。
        embedder 不可用时退化为按 confidence/support_count 排序的 list_by_concept。

        per_concept_cap：每个 concept 最多召回多少条 facet。默认 None 表示不限制
        （沿用旧的"先到先得 top_k"语义）。retrieve_service 会传入明确的配额，
        防止某个高频 concept 把 top_k 占满、其它 concept 一条都召不到。
        """
        if not concept_ids:
            return []

        cap = int(per_concept_cap) if per_concept_cap and per_concept_cap > 0 else 0

        store = get_vector_store()
        # 向量路径
        if store.enabled and query:
            # 候选池适当放大：cap > 0 时按 cap × N concepts × 2 取上限
            candidate_k = top_k * 3
            if cap > 0:
                candidate_k = max(candidate_k, cap * len(concept_ids) * 2)
            hits = store.search(COLLECTION_FACET, query, top_k=candidate_k)

            results: list[FacetBrief] = []
            per_concept_count: dict[str, int] = {}
            for h in hits:
                payload = h.get("payload") or {}
                cid = payload.get("concept_id")
                if cid not in concept_ids:
                    continue
                # 按 concept 配额限流（cap=0 表示不限）
                if cap > 0 and per_concept_count.get(cid, 0) >= cap:
                    continue
                fid = payload.get("facet_id") or h.get("biz_id")
                if not fid:
                    continue
                row = self._fetchone(
                    "SELECT * FROM facet WHERE id=? AND status='active'", (fid,)
                )
                if not row:
                    continue
                if kinds and row["kind"] not in kinds:
                    continue
                results.append(_row_to_brief(row, score=float(h["score"])))
                per_concept_count[cid] = per_concept_count.get(cid, 0) + 1
                if len(results) >= top_k:
                    break
            if results:
                return results

        # 退化：按概念顺序拉每个概念的高置信 facet
        out: list[FacetBrief] = []
        # 退化路径下 cap 优先于 top_k 平均分配，避免大子图把每 concept 配额压到 0
        if cap > 0:
            per = cap
        else:
            per = max(1, top_k // max(1, len(concept_ids)))
        for cid in concept_ids:
            for f in self.list_by_concept(cid, kinds=kinds, limit=per):
                out.append(
                    FacetBrief(
                        id=f.id,
                        concept_id=f.concept_id,
                        kind=f.kind,
                        content=f.content,
                        confidence=f.confidence,
                        support_count=f.support_count,
                        score=f.confidence,
                    )
                )
                if len(out) >= top_k:
                    return out
        return out[:top_k]

    # ---------- 向量同步 ----------

    def _reindex(self, facet_id: str, concept_brief: Any = None) -> bool:
        """重建一条 facet 的向量。返回 True 表示向量库有写入。"""
        f = self.get_by_id(facet_id)
        if not f:
            return False
        emb_text = build_facet_text(f, concept=concept_brief)
        vid, model = get_vector_store().upsert(
            COLLECTION_FACET,
            biz_id=facet_id,
            text=emb_text,
            payload={
                "facet_id": facet_id,
                "concept_id": f.concept_id,
                "kind": f.kind,
            },
        )
        if vid:
            with get_kg_db() as conn:
                conn.execute(
                    "UPDATE facet SET embedding_model=?, vector_id=? WHERE id=?",
                    (model, vid, facet_id),
                )
                conn.commit()
            return True
        return False
