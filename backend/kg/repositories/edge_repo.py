"""
ConceptEdgeRepository：概念关系数据访问层

支持反馈强化字段：support_count / origin / origin_ref。
"""

from __future__ import annotations

from typing import Optional

from ..database import get_kg_db
from ..models import ConceptEdgeCreate, ConceptEdgeSchema, VALID_RELATION_TYPES
from .base import KGBaseRepo, dumps, loads, new_id, utcnow_str


def _row_to_schema(row: dict) -> ConceptEdgeSchema:
    return ConceptEdgeSchema(
        id=row["id"],
        src_id=row["src_id"],
        dst_id=row["dst_id"],
        relation_type=row["relation_type"],
        weight=row["weight"],
        status=row["status"],
        support_count=row["support_count"] if "support_count" in row.keys() else 0,
        origin=row["origin"] if "origin" in row.keys() else "manual",
        origin_ref=loads(row["origin_ref"] if "origin_ref" in row.keys() else "{}", {}),
        created_by=row["created_by"] or "",
        created_at=row["created_at"],
    )


class ConceptEdgeRepository(KGBaseRepo):
    def create(self, data: ConceptEdgeCreate) -> ConceptEdgeSchema:
        if data.relation_type not in VALID_RELATION_TYPES:
            raise ValueError(f"非法 relation_type: {data.relation_type}")
        if data.src_id == data.dst_id:
            raise ValueError("src_id 与 dst_id 不能相同")
        # 调用方派生过稳定 id (OKF 通路) 就用它; 否则回退 UUID。
        eid = data.id or new_id()
        now = utcnow_str()
        with get_kg_db() as conn:
            conn.execute(
                """
                INSERT INTO concept_edge
                  (id, src_id, dst_id, relation_type, weight, status,
                   support_count, origin, origin_ref, created_by, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    eid,
                    data.src_id,
                    data.dst_id,
                    data.relation_type,
                    max(0.0, min(1.0, data.weight)),
                    data.status,
                    0,
                    data.origin,
                    dumps(data.origin_ref or {}),
                    data.created_by,
                    now,
                ),
            )
            conn.commit()
        return self.get_by_id(eid)

    def get_by_id(self, edge_id: str) -> Optional[ConceptEdgeSchema]:
        row = self._fetchone("SELECT * FROM concept_edge WHERE id=?", (edge_id,))
        return _row_to_schema(row) if row else None

    def find(
        self, src_id: str, dst_id: str, relation_type: str
    ) -> Optional[ConceptEdgeSchema]:
        row = self._fetchone(
            "SELECT * FROM concept_edge WHERE src_id=? AND dst_id=? AND relation_type=?",
            (src_id, dst_id, relation_type),
        )
        return _row_to_schema(row) if row else None

    def neighbors(
        self,
        concept_id: str,
        relation_types: Optional[list[str]] = None,
        direction: str = "out",  # out | in | both
        status: str = "approved",
        limit: int = 50,
    ) -> list[ConceptEdgeSchema]:
        clauses: list[str] = []
        params: list = []

        if direction == "out":
            clauses.append("src_id=?")
            params.append(concept_id)
        elif direction == "in":
            clauses.append("dst_id=?")
            params.append(concept_id)
        else:
            clauses.append("(src_id=? OR dst_id=?)")
            params.extend([concept_id, concept_id])

        if status:
            clauses.append("status=?")
            params.append(status)

        if relation_types:
            placeholders = ",".join("?" for _ in relation_types)
            clauses.append(f"relation_type IN ({placeholders})")
            params.extend(relation_types)

        sql = (
            "SELECT * FROM concept_edge WHERE "
            + " AND ".join(clauses)
            + " ORDER BY weight DESC LIMIT ?"
        )
        params.append(limit)
        rows = self._fetchall(sql, tuple(params))
        return [_row_to_schema(r) for r in rows]

    def increment_support(self, edge_id: str, by: int = 1) -> bool:
        """边被对话再次印证时调用：support_count += by。聚合器路径用。"""
        with get_kg_db() as conn:
            cur = conn.execute(
                "UPDATE concept_edge SET support_count = support_count + ? WHERE id=?",
                (by, edge_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def update_weight(self, edge_id: str, weight: float) -> bool:
        with get_kg_db() as conn:
            cur = conn.execute(
                "UPDATE concept_edge SET weight=? WHERE id=?",
                (max(0.0, min(1.0, weight)), edge_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def update_status(self, edge_id: str, status: str) -> bool:
        with get_kg_db() as conn:
            cur = conn.execute(
                "UPDATE concept_edge SET status=? WHERE id=?",
                (status, edge_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete(self, edge_id: str) -> bool:
        with get_kg_db() as conn:
            cur = conn.execute("DELETE FROM concept_edge WHERE id=?", (edge_id,))
            conn.commit()
            return cur.rowcount > 0

    # ---------- 增量同步专用 ----------

    def upsert(self, data: ConceptEdgeCreate) -> tuple[ConceptEdgeSchema, str]:
        """OKF 增量同步专用：按派生 id 写入或忽略。

        语义：
          - 不存在 → 等价 self.create(data)，action='created'
          - 已存在 → 直接跳过，action='unchanged'

        OKF 通路下 edge 的 weight=1.0 / status='approved' / origin='okf'
        都是固定值；只要 (src, dst, relation) 没变，eid 就不变，无需 update。

        约定：调用方必须传 data.id（OKF 用 derive_edge_id 派生）。
        """
        if not data.id:
            raise ValueError("upsert 必须传入 data.id（派生 id）")

        existing = self.get_by_id(data.id)
        if existing is not None:
            return existing, "unchanged"
        return self.create(data), "created"

    def list_by_origin_and_src(
        self, src_id: str, origin: str = "okf"
    ) -> list[ConceptEdgeSchema]:
        """列出某 src 在某 origin 下的所有 edge（增量同步算 diff 用）。"""
        rows = self._fetchall(
            "SELECT * FROM concept_edge WHERE src_id=? AND origin=?",
            (src_id, origin),
        )
        return [_row_to_schema(r) for r in rows]
