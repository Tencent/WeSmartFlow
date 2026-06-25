"""
ProposalRepository：KG 硬变更的统一入口

所有对 concept / facet / edge 的"新增/修改/合并/下线"都必须先创建 Proposal，
经审核（approved）后由 ProposalService 在事务内落库。

本 repo 只负责 CRUD；真正执行 op 的逻辑在 services/proposal_service.py。
"""

from __future__ import annotations

from typing import Any, Optional

from ..database import get_kg_db
from ..models import PROPOSAL_OPS, ProposalCreate, ProposalSchema
from .base import KGBaseRepo, dumps, loads, new_id, utcnow_str


def _row_to_schema(row: dict) -> ProposalSchema:
    return ProposalSchema(
        id=row["id"],
        op=row["op"],
        proposer=row["proposer"],
        payload=loads(row["payload"], {}),
        target_concept_id=row["target_concept_id"],
        target_facet_id=row["target_facet_id"],
        target_edge_id=row["target_edge_id"],
        session_id=row["session_id"],
        evidence=loads(row["evidence"], {}),
        status=row["status"],
        reviewer_id=row["reviewer_id"] or "",
        review_note=row["review_note"] or "",
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
    )


class ProposalRepository(KGBaseRepo):
    def create(self, data: ProposalCreate) -> ProposalSchema:
        if data.op not in PROPOSAL_OPS:
            raise ValueError(f"非法 proposal op: {data.op}")
        pid = new_id()
        now = utcnow_str()
        with get_kg_db() as conn:
            conn.execute(
                """
                INSERT INTO proposal
                  (id, op, proposer, payload, target_concept_id, target_facet_id,
                   target_edge_id, session_id, evidence, status,
                   reviewer_id, review_note, created_at, reviewed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    pid,
                    data.op,
                    data.proposer,
                    dumps(data.payload or {}),
                    data.target_concept_id,
                    data.target_facet_id,
                    data.target_edge_id,
                    data.session_id,
                    dumps(data.evidence or {}),
                    "pending",
                    "",
                    "",
                    now,
                    None,
                ),
            )
            conn.commit()
        return self.get_by_id(pid)  # type: ignore[return-value]

    def get_by_id(self, proposal_id: str) -> Optional[ProposalSchema]:
        row = self._fetchone("SELECT * FROM proposal WHERE id=?", (proposal_id,))
        return _row_to_schema(row) if row else None

    def list_pending(
        self,
        op: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProposalSchema]:
        clauses = ["status='pending'"]
        params: list[Any] = []
        if op:
            clauses.append("op=?")
            params.append(op)
        sql = (
            "SELECT * FROM proposal WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at ASC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        rows = self._fetchall(sql, tuple(params))
        return [_row_to_schema(r) for r in rows]

    def list_by_status(
        self,
        status: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProposalSchema]:
        rows = self._fetchall(
            "SELECT * FROM proposal WHERE status=? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
        )
        return [_row_to_schema(r) for r in rows]

    def update_status(
        self,
        proposal_id: str,
        status: str,
        reviewer_id: str = "",
        review_note: str = "",
    ) -> bool:
        now = utcnow_str()
        with get_kg_db() as conn:
            cur = conn.execute(
                "UPDATE proposal SET status=?, reviewer_id=?, review_note=?, "
                "reviewed_at=? WHERE id=?",
                (status, reviewer_id, review_note, now, proposal_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def merge_evidence(self, proposal_id: str, extra: dict) -> bool:
        """把 extra 字典合并到 proposal.evidence 现有 JSON 上（浅合并）。

        ProposalService.approve 用它把新建实体的 id（created_concept_id 等）
        写回 evidence，便于上层 agent 接住结果。
        """
        if not extra:
            return False
        cur = self.get_by_id(proposal_id)
        if not cur:
            return False
        merged = {**(cur.evidence or {}), **extra}
        with get_kg_db() as conn:
            row = conn.execute(
                "UPDATE proposal SET evidence=? WHERE id=?",
                (dumps(merged), proposal_id),
            )
            conn.commit()
            return row.rowcount > 0
