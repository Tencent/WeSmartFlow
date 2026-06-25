"""
backend → KG 子模块的业务门面（最小形态）

设计原则
========
1. **单一入口**：backend 业务侧（routers / services）只 import 这一个文件，
   不直接 import kg.repositories.* 或 services.*。
2. **薄封装**：本文件不实现业务逻辑，仅做参数转换 + 异常归一化。
3. **Agent 闭环（最小形态）**：
   - **观察轨道**: agent 在对话中写 observation → 后台聚合 → LLM 归纳出共性
     → 产 ``suggest_facet_pattern`` proposal（pending），等管理员人审落 facet
   - **建议轨道**: agent 提议「KG 中缺一个概念」 → 直接产 ``suggest_missing_concept``
     proposal（pending），等管理员看到后自行建档
4. **写入收敛**：教学 Agent 对 KG 的唯一"间接写入"入口是
   ``agent_propose_missing_concept`` 和 ``agent_record_observation``；
   不再开放任何「直接构造 add_facet / add_edge」的接口，也不再有
   AutoApproveGate / build_queue / ConceptBuilderService 的自动建档通路。
"""

from __future__ import annotations

import logging
from typing import Optional

from kg import (
    AggregatorService,
    ConceptRepository,
    ConceptResolveItem,
    ObservationCreate,
    ObservationSchema,
    ProposalCreate,
    ProposalService,
    RetrieveRequest,
    RetrieveResponse,
    RetrieveService,
)

logger = logging.getLogger(__name__)

# ============================================================
# 检索（前端 / Agent 主用）
# ============================================================


def retrieve(req: RetrieveRequest) -> RetrieveResponse:
    """Graph RAG 两段式检索：query → 入口概念 → 子图扩展 → facet 召回。"""
    return RetrieveService().retrieve(req)


def resolve_terms(terms: list[str], top_k: int = 1) -> list[ConceptResolveItem]:
    """实体链接：自由文本 → concept_id（精确名 → 别名 → 向量召回）。"""
    repo = ConceptRepository()
    out: list[ConceptResolveItem] = []
    for term in terms:
        items = repo.resolve(term, top_k=top_k)
        if items:
            out.extend(items)
        else:
            out.append(ConceptResolveItem(term=term, match_type="none"))
    return out


# ============================================================
# 反馈闭环：观察写入（agent 在对话中主动调用）
# ============================================================


def submit_observation(data: ObservationCreate) -> ObservationSchema:
    """agent 在对话中写入一条对用户的观察；不做任何审核，立即落库。

    聚合器会异步按 (concept_id, observation_type) 分桶消费，
    达阈后调 LLM 归纳成"共性提议"（suggest_facet_pattern proposal），
    等管理员审阅后才落成 facet。
    """
    return AggregatorService().submit_observation(data)


def run_aggregator_once(batch_size: int = 200) -> dict:
    """供后台/管理脚本触发一次聚合。生产可改成定时任务。"""
    return AggregatorService().run_once(batch_size=batch_size)


# ============================================================
# Agent 自治闭环 — 对 LLM 透明的「动词工具」语义层
# ----------------------------------------------------------------
# 设计原则:
#   - 教学 Agent 只是「发现者 + 观察者」:
#       · 发现 KG 缺概念 → agent_propose_missing_concept（产一条 pending proposal）
#       · 观察到学生反应 → agent_record_observation（记录观察，由聚合器归纳）
#   - 不再有 add_concept / add_facet / link_concepts 等直写工具。
#   - propose_missing_concept 直接产 ``suggest_missing_concept`` proposal,
#     永远 pending，由管理员人工处理；不再有 AutoApproveGate / build_queue / 自动建档。
# ============================================================


def agent_proposer(user_id: str, session_id: str = "") -> str:
    parts = ["agent", user_id or "anonymous"]
    if session_id:
        parts.append(session_id)
    return ":".join(parts)


def agent_propose_missing_concept(
    *,
    user_id: str,
    session_id: str,
    concept_name: str,
    reason_brief: str,
) -> dict:
    """教学 Agent 发现 KG 中缺一个概念,提议「该收」。

    流程:
      1) 先 resolve(concept_name),命中 exact / alias 直接返回 matched
         (告诉 Agent 这个已在 KG 里,下次别重复提)
      2) 再查 proposal 表,若已有同名 pending 的 ``suggest_missing_concept``,
         返回 matched_pending（避免反复刷出重复提议）
      3) 否则 → 直接产一条 ``suggest_missing_concept`` proposal（pending），
         等管理员审阅。**不会自动建档、不入任何队列。**

    Returns:
        ``{"status": "matched"|"matched_pending"|"proposed"|"rejected",
            "concept_id":   str|None,    # matched 时返回现有 id
            "proposal_id":  str|None,    # proposed/matched_pending 时返回 proposal id
            "reason":       str}``
    """
    name = (concept_name or "").strip()
    if not name:
        return {
            "status": "rejected",
            "concept_id": None,
            "proposal_id": None,
            "reason": "concept_name 为空",
        }

    reason = (reason_brief or "").strip()
    if not reason:
        return {
            "status": "rejected",
            "concept_id": None,
            "proposal_id": None,
            "reason": "reason_brief 为空",
        }

    # 1) 先 resolve 防重（已在 KG 中存在则直接告知 agent）
    items = resolve_terms([name], top_k=1)
    if items and items[0].match_type in ("exact", "alias") and items[0].concept_id:
        return {
            "status": "matched",
            "concept_id": items[0].concept_id,
            "proposal_id": None,
            "reason": f"已有同名概念 (match={items[0].match_type})",
        }

    # 2) 再查 pending 同名提议（避免反复刷重复 proposal）
    try:
        from kg.database import get_kg_db

        with get_kg_db() as conn:
            row = conn.execute(
                "SELECT id FROM proposal "
                "WHERE op='suggest_missing_concept' AND status='pending' "
                "AND json_extract(payload,'$.concept_name')=? "
                "ORDER BY created_at DESC LIMIT 1",
                (name,),
            ).fetchone()
        if row:
            return {
                "status": "matched_pending",
                "concept_id": None,
                "proposal_id": row["id"],
                "reason": "已有同名提议在待审清单中",
            }
    except Exception:  # pylint: disable=broad-except
        # 查重异常不阻塞主流程，继续走创建（最坏情况就是重复一条 pending）
        logger.exception(
            "agent_propose_missing_concept pending 查重失败，降级为直接创建"
        )

    # 3) 直接产一条 pending proposal
    try:
        proposal = ProposalService().create(
            ProposalCreate(
                op="suggest_missing_concept",
                proposer=agent_proposer(user_id, session_id),
                payload={
                    "concept_name": name,
                    "reason_brief": reason,
                },
                session_id=session_id or None,
            )
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("agent_propose_missing_concept 创建 proposal 失败")
        return {
            "status": "rejected",
            "concept_id": None,
            "proposal_id": None,
            "reason": f"create proposal failed: {exc}",
        }

    return {
        "status": "proposed",
        "concept_id": None,
        "proposal_id": proposal.id,
        "reason": "已记入待审清单，等待管理员处理",
    }


def agent_record_observation(
    *,
    user_id: str,
    session_id: str,
    concept: str,
    observation_type: str,
    description: str,
    agent_confidence: float = 0.6,
    related_facet_id: Optional[str] = None,
) -> dict:
    """Agent 自治：写一条对用户的观察。

    工具层只需提供概念名 + 观察内容，本函数内部完成 concept_id 解析。
    解析策略（只查不建，软失败）：
      1) resolve(concept) 命中 exact / alias / vector → 拿到 concept_id 落库
      2) 未命中 → 不创建占位概念，直接返回 status='skipped'，不阻塞对话

    Returns:
        ``{"status": "recorded"|"skipped",
            "observation_id": str|None,
            "concept_id":     str|None,
            "matched_name":   str|None,
            "match_type":     str,
            "reason":         str}``
    """
    name = (concept or "").strip()
    if not name:
        return {
            "status": "skipped",
            "observation_id": None,
            "concept_id": None,
            "matched_name": None,
            "match_type": "none",
            "reason": "concept 为空",
        }

    desc = (description or "").strip()
    if not desc:
        return {
            "status": "skipped",
            "observation_id": None,
            "concept_id": None,
            "matched_name": None,
            "match_type": "none",
            "reason": "description 为空",
        }

    items = resolve_terms([name], top_k=1)
    top = items[0] if items else None
    if not top or top.match_type == "none" or not top.concept_id:
        return {
            "status": "skipped",
            "observation_id": None,
            "concept_id": None,
            "matched_name": None,
            "match_type": "none",
            "reason": (
                f"概念「{name}」未在 KG 中找到匹配，"
                "本条观察未记录；如需引入新概念请调 kg_propose_missing_concept。"
            ),
        }

    obs = submit_observation(
        ObservationCreate(
            concept_id=top.concept_id,
            observation_type=observation_type,
            description=desc,
            user_id=user_id,
            session_id=session_id,
            related_facet_id=related_facet_id,
            agent_confidence=max(0.0, min(1.0, float(agent_confidence))),
        )
    )
    return {
        "status": "recorded",
        "observation_id": obs.id,
        "concept_id": top.concept_id,
        "matched_name": top.canonical_name,
        "match_type": top.match_type,
        "reason": f"matched via {top.match_type}",
    }
