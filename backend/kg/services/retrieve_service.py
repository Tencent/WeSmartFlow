"""
RetrieveService：Graph RAG 两段式检索（concept + facet）

流水线：
  Stage 1 [Anchor]   query → 入口 concept（整句 embedding 在 concept 向量库做近邻检索）
                     拿不到强候选时，cos∈[weak, min) 的概念会作为 weak_candidates 返回。
  Stage 2 [Expand]   入口 → 沿"被 query 激活的关系类型"扩展邻居 → 子图
  Stage 3 [Facets]   在子图概念集合内召回相关 facet（教法 + 共性反馈）

设计要点：
  - 原 exhibit / chunk 二级体系退役，统一用 facet 承载所有可检索内容
  - 子图为空 = 知识范围外，直接空（不做"假兜底"）
"""

from __future__ import annotations

import logging
from typing import Optional

from ..config import (
    KG_ANCHOR_GAP_RATIO,
    KG_ANCHOR_MAX_ENTRIES,
    KG_ANCHOR_MIN_SCORE,
    KG_ANCHOR_TOPK,
    KG_ANCHOR_WEAK_SCORE,
    KG_NEIGHBOR_FANOUT,
    KG_REL_WEIGHT_FLOOR,
)
from ..embedder import get_embedder
from ..models import (
    ConceptBrief,
    FacetBrief,
    RetrieveRequest,
    RetrieveResponse,
    SubgraphConcept,
)
from ..relation_semantics import score_relations, softmax_normalize
from ..repositories import (
    ConceptEdgeRepository,
    ConceptRepository,
    FacetRepository,
)
from ..vector_store import COLLECTION_CONCEPT, get_vector_store

logger = logging.getLogger(__name__)

_ENTRY_BASE_SCORE = 1.0  # 入口节点固定分


class RetrieveService:
    def __init__(self) -> None:
        self.concept_repo = ConceptRepository()
        self.edge_repo = ConceptEdgeRepository()
        self.facet_repo = FacetRepository()

    # ============================================================
    # 主入口
    # ============================================================

    def retrieve(self, req: RetrieveRequest) -> RetrieveResponse:
        degraded = False
        degraded_reason = ""

        # ---- Stage 1: 锚定入口 ----
        entry_briefs, weak_candidates, anchor_reason = self._anchor(req)
        entry_ids = [c.id for c in entry_briefs]
        if not entry_briefs:
            degraded = True
            degraded_reason = anchor_reason or "未找到符合阈值的入口概念"

        # 记录被走过的边,稍后异步累加 support_count
        traversed_edge_ids: list[str] = []

        # ---- 关系语义打分 ----
        embedder = get_embedder()
        q_emb: list[float] = []
        if (
            req.graph_expand
            and embedder
            and getattr(embedder, "dim", 0) > 0
            and req.query
        ):
            try:
                q_emb = embedder.embed_one(req.query)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("retrieve: query 嵌入失败，退化为非图模式 err=%s", exc)
                q_emb = []
                degraded = True
                degraded_reason = degraded_reason or f"query 嵌入失败: {exc}"

        rel_scores = score_relations(q_emb) if q_emb else {}
        rel_dist = softmax_normalize(rel_scores, temperature=0.08)

        # ---- Stage 2: 图扩展 ----
        neighbor_budget = max(0, req.max_subgraph_size - len(entry_ids))
        if entry_ids and req.graph_expand and rel_scores and neighbor_budget > 0:
            subgraph_nodes = self._expand_subgraph(
                entry_briefs=entry_briefs,
                rel_scores=rel_scores,
                hops=max(1, req.expand_hops),
                neighbor_budget=neighbor_budget,
                traversed_edge_ids=traversed_edge_ids,
            )
        else:
            subgraph_nodes = [
                SubgraphConcept(concept=c, is_entry=True, score=_ENTRY_BASE_SCORE)
                for c in entry_briefs
            ]

        subgraph_concept_ids = [n.concept.id for n in subgraph_nodes]

        # ---- Stage 3: 召回 facet ----
        facets: list[FacetBrief] = []
        if req.need_facets and subgraph_concept_ids:
            facets = self._select_facets(
                req=req, subgraph_concept_ids=subgraph_concept_ids
            )

        # ---- 反馈强化:被走过的 edge 累加 support_count(失败不影响响应) ----
        if traversed_edge_ids:
            self._increment_edge_support_async(traversed_edge_ids)

        return RetrieveResponse(
            concepts=entry_briefs,
            facets=facets,
            subgraph=subgraph_nodes,
            relation_weights=rel_scores,
            relation_dist=rel_dist,
            weak_candidates=weak_candidates,
            degraded=degraded,
            degraded_reason=degraded_reason,
        )

    # ============================================================
    # Stage 1: 入口锚定
    # ============================================================

    def _anchor(
        self, req: RetrieveRequest
    ) -> tuple[list[ConceptBrief], list[ConceptBrief], str]:
        results: list[ConceptBrief] = []
        weak: list[ConceptBrief] = []
        seen: set[str] = set()

        query = (req.query or "").strip()
        if not query:
            return results, weak, "query 为空"

        store = get_vector_store()
        if not store.enabled:
            logger.warning("_anchor: vector store 未启用，无法锚定入口")
            return results, weak, "向量库未启用（embedder 不可用）"

        min_score = (
            req.anchor_min_score
            if req.anchor_min_score is not None
            else KG_ANCHOR_MIN_SCORE
        )
        max_entries = (
            req.anchor_max_entries
            if req.anchor_max_entries is not None
            else KG_ANCHOR_MAX_ENTRIES
        )

        try:
            hits = store.search(COLLECTION_CONCEPT, query, top_k=KG_ANCHOR_TOPK)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("_anchor: 向量召回失败 err=%s", exc)
            return results, weak, f"向量召回异常: {exc}"

        if not hits:
            # 区分两种空召回:库内根本没 concept vs 召回路径异常但无报错
            try:
                with_data = self.concept_repo.exists_any_approved()
            except Exception:  # pylint: disable=broad-except
                with_data = None
            if with_data is False:
                return results, weak, "KG 库内无 approved concept(尚未建档)"
            return results, weak, "向量库无任何返回"

        top_score = float(hits[0]["score"])
        score_floor = max(min_score, top_score * KG_ANCHOR_GAP_RATIO)

        for h in hits:
            score = float(h["score"])
            cid = h["payload"].get("concept_id") or h["biz_id"]
            if not cid or cid in seen:
                continue
            c = self.concept_repo.follow_merge(cid)
            if not c or c.status != "approved":
                continue
            brief = _to_brief(c)

            if score >= score_floor and len(results) < max_entries:
                seen.add(c.id)
                results.append(brief)
            elif score >= KG_ANCHOR_WEAK_SCORE:
                if len(weak) < 5:
                    seen.add(c.id)
                    weak.append(brief)

        reason = ""
        if not results:
            reason = (
                f"top1 cos={top_score:.3f} 低于阈值 {min_score:.2f}"
                if top_score < min_score
                else "无候选通过筛选"
            )
        else:
            weak = []
        return results, weak, reason

    # ============================================================
    # Stage 2: 图扩展
    # ============================================================

    def _expand_subgraph(
        self,
        entry_briefs: list[ConceptBrief],
        rel_scores: dict[str, float],
        hops: int,
        neighbor_budget: int,
        traversed_edge_ids: Optional[list[str]] = None,
    ) -> list[SubgraphConcept]:
        nodes: dict[str, SubgraphConcept] = {}
        for c in entry_briefs:
            nodes[c.id] = SubgraphConcept(
                concept=c, is_entry=True, score=_ENTRY_BASE_SCORE
            )

        if neighbor_budget <= 0:
            return list(nodes.values())

        active_rels = [r for r, s in rel_scores.items() if s >= KG_REL_WEIGHT_FLOOR]
        if not active_rels:
            return list(nodes.values())

        neighbor_pool: dict[str, SubgraphConcept] = {}
        # 候选邻居 → 它是经由哪条 edge 第一次进入 pool 的(用于 support_count 反馈)
        neighbor_via_edge: dict[str, str] = {}
        frontier: list[str] = [c.id for c in entry_briefs]

        for hop in range(hops):
            decay = 0.6**hop
            next_frontier: list[str] = []

            for src_id in frontier:
                edges = self.edge_repo.neighbors(
                    concept_id=src_id,
                    relation_types=active_rels,
                    direction="both",
                    limit=KG_NEIGHBOR_FANOUT,
                )
                for e in edges:
                    nbr_id = e.dst_id if e.src_id == src_id else e.src_id
                    if nbr_id == src_id or nbr_id in nodes:
                        continue

                    rel_w = rel_scores.get(e.relation_type, 0.0)
                    candidate_score = decay * float(e.weight) * float(rel_w)

                    existing = neighbor_pool.get(nbr_id)
                    if existing and existing.score >= candidate_score:
                        continue

                    nbr = self.concept_repo.follow_merge(nbr_id)
                    if not nbr or nbr.status != "approved":
                        continue
                    neighbor_pool[nbr_id] = SubgraphConcept(
                        concept=_to_brief(nbr),
                        is_entry=False,
                        via_relation=e.relation_type,
                        via_concept_id=src_id,
                        score=candidate_score,
                    )
                    neighbor_via_edge[nbr_id] = e.id
                    next_frontier.append(nbr_id)

            if not next_frontier:
                break
            frontier = next_frontier

        top_neighbors = sorted(neighbor_pool.values(), key=lambda n: -n.score)[
            :neighbor_budget
        ]
        # 只把真正进入子图的那些邻居所对应的 edge 记入反馈队列
        if traversed_edge_ids is not None:
            for n in top_neighbors:
                eid = neighbor_via_edge.get(n.concept.id)
                if eid:
                    traversed_edge_ids.append(eid)
        return list(nodes.values()) + top_neighbors

    # ============================================================
    # Stage 3: facet 召回
    # ============================================================

    def _select_facets(
        self,
        req: RetrieveRequest,
        subgraph_concept_ids: list[str],
    ) -> list[FacetBrief]:
        per_concept = max(1, req.top_k_facets_per_concept)
        # 总预算 = 每个概念配额 × 概念数(再做向量重排,留点余量)
        total_budget = per_concept * max(1, len(subgraph_concept_ids))

        return self.facet_repo.search(
            query=req.query,
            concept_ids=subgraph_concept_ids,
            kinds=req.facet_kinds or None,
            top_k=total_budget,
            per_concept_cap=per_concept,
        )

    # ============================================================
    # 反馈强化:异步累加 edge support_count
    # ============================================================

    def _increment_edge_support_async(self, edge_ids: list[str]) -> None:
        """开后台线程累加被本次检索走过的边 support_count。

        - 不阻塞读路径,失败仅打 warning;
        - 单线程处理一次性的小列表,避免引入复杂调度。
        """
        import threading

        def _worker(ids: list[str]) -> None:
            for eid in ids:
                try:
                    self.edge_repo.increment_support(eid, by=1)
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning(
                        "retrieve: edge support_count 累加失败 eid=%s err=%s",
                        eid,
                        exc,
                    )

        try:
            t = threading.Thread(target=_worker, args=(list(edge_ids),), daemon=True)
            t.start()
        except Exception:  # pylint: disable=broad-except
            logger.exception("retrieve: 启动 support_count 累加线程失败,跳过")


# ============================================================
# 工具函数
# ============================================================


def _to_brief(c) -> ConceptBrief:
    return ConceptBrief(
        id=c.id,
        slug=c.slug,
        canonical_name=c.canonical_name,
        summary=c.summary,
        subject=c.subject,
        difficulty=c.difficulty,
    )
