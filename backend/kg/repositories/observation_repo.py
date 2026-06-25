"""
ObservationRepository：对话过程中 agent 主动写入的对用户的观察

这张表只存"行为/状态/反应"的笔记，不存知识本身。
聚合器周期性按 (concept_id, observation_type) 分桶，达阈值后调 LLM
做归纳，把跨用户共性升格为 Facet（通过 Proposal 走审核）。
"""

from __future__ import annotations

from typing import Any, Optional

from ..database import get_kg_db
from ..models import OBSERVATION_TYPES, ObservationCreate, ObservationSchema
from .base import KGBaseRepo, dumps, loads, new_id, utcnow_str


def _row_to_schema(row: dict) -> ObservationSchema:
    return ObservationSchema(
        id=row["id"],
        concept_id=row["concept_id"],
        observation_type=row["observation_type"],
        description=row["description"] or "",
        user_id=row["user_id"] or "",
        session_id=row["session_id"] or "",
        related_facet_id=row["related_facet_id"],
        user_state_snapshot=loads(row["user_state_snapshot"], {}),
        evidence=loads(row["evidence"], {}),
        agent_confidence=row["agent_confidence"],
        processed_at=row["processed_at"],
        derived_proposal_id=row["derived_proposal_id"],
        created_at=row["created_at"],
    )


class ObservationRepository(KGBaseRepo):
    def create(self, data: ObservationCreate) -> ObservationSchema:
        if data.observation_type not in OBSERVATION_TYPES:
            raise ValueError(
                f"非法 observation_type={data.observation_type}; "
                f"必须为 {sorted(OBSERVATION_TYPES)} 之一"
            )
        oid = new_id()
        now = utcnow_str()
        with get_kg_db() as conn:
            conn.execute(
                """
                INSERT INTO observation
                  (id, concept_id, observation_type, description,
                   user_id, session_id, related_facet_id,
                   user_state_snapshot, evidence, agent_confidence,
                   processed_at, derived_proposal_id, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    oid,
                    data.concept_id,
                    data.observation_type,
                    data.description,
                    data.user_id,
                    data.session_id,
                    data.related_facet_id,
                    dumps(data.user_state_snapshot or {}),
                    dumps(data.evidence or {}),
                    max(0.0, min(1.0, float(data.agent_confidence))),
                    None,
                    None,
                    now,
                ),
            )
            conn.commit()
        return self.get_by_id(oid)  # type: ignore[return-value]

    def get_by_id(self, observation_id: str) -> Optional[ObservationSchema]:
        row = self._fetchone("SELECT * FROM observation WHERE id=?", (observation_id,))
        return _row_to_schema(row) if row else None

    # ---------- 聚合器查询 ----------

    def count_unprocessed_by_bucket(self) -> list[dict[str, Any]]:
        """统计每个 (concept_id, observation_type) 桶下未处理的观察数。"""
        rows = self._fetchall(
            """
            SELECT concept_id, observation_type, COUNT(*) AS cnt
            FROM observation
            WHERE processed_at IS NULL
            GROUP BY concept_id, observation_type
            """
        )
        return [
            {
                "concept_id": r["concept_id"],
                "observation_type": r["observation_type"],
                "count": int(r["cnt"]),
            }
            for r in rows
        ]

    def list_unprocessed_in_bucket(
        self,
        concept_id: str,
        observation_type: str,
        limit: int = 50,
    ) -> list[ObservationSchema]:
        rows = self._fetchall(
            """
            SELECT * FROM observation
            WHERE concept_id=? AND observation_type=? AND processed_at IS NULL
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (concept_id, observation_type, limit),
        )
        return [_row_to_schema(r) for r in rows]

    def mark_processed(
        self,
        observation_ids: list[str],
        derived_proposal_id: Optional[str] = None,
    ) -> int:
        if not observation_ids:
            return 0
        placeholders = ",".join("?" for _ in observation_ids)
        now = utcnow_str()
        with get_kg_db() as conn:
            cur = conn.execute(
                f"UPDATE observation SET processed_at=?, derived_proposal_id=? "
                f"WHERE id IN ({placeholders})",
                tuple([now, derived_proposal_id] + list(observation_ids)),
            )
            conn.commit()
            return cur.rowcount

    def list_by_session(self, session_id: str) -> list[ObservationSchema]:
        rows = self._fetchall(
            "SELECT * FROM observation WHERE session_id=? ORDER BY created_at ASC",
            (session_id,),
        )
        return [_row_to_schema(r) for r in rows]
