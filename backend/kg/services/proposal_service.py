"""
ProposalService:轻提议（最小形态）的审核入口

设计
====
Proposal 表只承载两类**轻量信号**给管理员看，**永远停在 pending**，
不会被任何后台流程自动 approve：

  - ``suggest_missing_concept``  教学 Agent 发现 KG 缺一个有教学价值的概念
                                  payload: {concept_name, reason_brief}
  - ``suggest_facet_pattern``    Aggregator 从一桶 observations 归纳出一个共性
                                  payload: {concept_id, kind, content,
                                            observation_ids, ...}

approve / reject 由人工触发：
  - approve(suggest_facet_pattern)  → 真把它落成一条 facet
  - approve(suggest_missing_concept) → 仅作为"已读/已采纳"的标记；真要建概念
    由管理员另行操作（本 op 的 payload 信息不足以建一个 concept）。
  - reject 任何 op → 仅打标，无副作用。

不再有 AutoApproveGate / concept_build_queue / ConceptBuilderService 等中间层。
"""

from __future__ import annotations

import logging
from typing import Optional

from ..models import (
    FacetCreate,
    ProposalCreate,
    ProposalSchema,
)
from ..repositories import (
    ConceptRepository,
    FacetRepository,
    ProposalRepository,
)

logger = logging.getLogger(__name__)


class ProposalService:
    def __init__(self) -> None:
        self.proposal_repo = ProposalRepository()
        self.concept_repo = ConceptRepository()
        self.facet_repo = FacetRepository()

    # ---------- 创建 ----------

    def create(self, data: ProposalCreate) -> ProposalSchema:
        """统一入口：把外部提议落成一条 pending proposal。"""
        return self.proposal_repo.create(data)

    # ---------- 审核（仅人工触发）----------

    def approve(
        self,
        proposal_id: str,
        reviewer_id: str = "",
        review_note: str = "",
    ) -> Optional[ProposalSchema]:
        p = self.proposal_repo.get_by_id(proposal_id)
        if not p:
            return None
        if p.status != "pending":
            logger.info("approve: proposal %s 已是 %s，跳过", proposal_id, p.status)
            return p

        try:
            applied = self._apply(p) or {}
        except Exception as exc:
            logger.exception("apply proposal 失败 id=%s op=%s err=%s", p.id, p.op, exc)
            self.proposal_repo.update_status(
                p.id,
                status="rejected",
                reviewer_id=reviewer_id or "system",
                review_note=f"apply failed: {exc}",
            )
            return self.proposal_repo.get_by_id(p.id)

        # 把 apply 副产物（如 created_facet_id）合并写回 evidence
        if applied:
            self.proposal_repo.merge_evidence(p.id, applied)

        self.proposal_repo.update_status(
            p.id,
            status="approved",
            reviewer_id=reviewer_id,
            review_note=review_note,
        )
        return self.proposal_repo.get_by_id(p.id)

    def reject(
        self,
        proposal_id: str,
        reviewer_id: str = "",
        review_note: str = "",
    ) -> Optional[ProposalSchema]:
        self.proposal_repo.update_status(
            proposal_id,
            status="rejected",
            reviewer_id=reviewer_id,
            review_note=review_note,
        )
        return self.proposal_repo.get_by_id(proposal_id)

    # ---------- op dispatch ----------

    def _apply(self, p: ProposalSchema) -> dict:
        """执行 proposal 的实际副作用。返回的 dict 会合并到 proposal.evidence。"""
        op = p.op
        payload = p.payload or {}

        if op == "suggest_missing_concept":
            # 这个 op 只是"建议管理员去建"，本身不带足够信息建 concept。
            # approve 时仅打标，不做副作用；管理员真要建概念请另行通过 OKF / 后台直接建。
            return {
                "applied": "noop",
                "note": (
                    "suggest_missing_concept approve 仅作为已采纳的标记；"
                    "真正建档请通过 OKF ingest 或后台直接调 concept_repo.create。"
                ),
            }

        if op == "suggest_facet_pattern":
            concept_id = (payload.get("concept_id") or "").strip()
            kind = (payload.get("kind") or "").strip()
            content = (payload.get("content") or "").strip()
            if not concept_id or not kind or not content:
                raise ValueError("suggest_facet_pattern 缺 concept_id / kind / content")
            concept = self.concept_repo.get_by_id(concept_id)
            if not concept:
                raise ValueError(f"concept {concept_id} 不存在")

            try:
                conf = float(payload.get("suggested_confidence") or 0.5)
            except (TypeError, ValueError):
                conf = 0.5

            facet = self.facet_repo.create(
                FacetCreate(
                    concept_id=concept_id,
                    kind=kind,
                    content=content,
                    confidence=max(0.1, min(0.9, conf)),
                    origin="dialog_aggregated",
                    origin_ref={
                        "source_proposal_id": p.id,
                        "observation_type": payload.get("observation_type"),
                        "observation_count": payload.get("observation_count"),
                        "user_count": payload.get("user_count"),
                        "session_ids": payload.get("session_ids") or [],
                        "rationale": payload.get("rationale", ""),
                        "observation_ids": payload.get("observation_ids") or [],
                    },
                    status="active",
                    created_by=f"reviewer:{p.id}",
                ),
                concept_brief=concept,
            )
            return {
                "applied": "created_facet",
                "created_facet_id": facet.id,
            }

        raise ValueError(
            f"未支持的 proposal op: {op}（当前仅 suggest_missing_concept / "
            "suggest_facet_pattern）"
        )
