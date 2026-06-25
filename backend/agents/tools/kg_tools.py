"""
KG 工具集 (kg_tools)

让教学 Agent 在对话中:
- 检索公共知识图谱 (kg_search / kg_resolve)
- 提议「KG 中缺失的概念」 (kg_propose_missing_concept) ← 唯一的写入入口
- 记录对当前用户的观察 (kg_record_observation),由后台聚合器周期性归纳成
  教学知识反哺 KG

设计原则
========
教学 Agent 只是「发现者 + 观察者」,不再扮演 KG 的维护者:
  - 不再有 add_concept / add_facet / link_concepts 等直写工具
  - 发现 KG 缺概念,只能提议「该收」(产一条 pending proposal,由管理员人工处理)
  - 发现学生反应/卡点,记录 observation,由 AggregatorService 跨用户归纳后
    产一条 suggest_facet_pattern proposal,同样交管理员人工处理
所有写入都同进程调用 services.kg_facade(无 HTTP)。
"""

from __future__ import annotations

import json
import logging

from agent_core.tool.base import BaseTool

from kg.models import (
    OBSERVATION_TYPES,
    RetrieveRequest,
)

logger = logging.getLogger(__name__)


# ============================================================
# kg.search — 检索公共知识图谱
# ============================================================


class KGSearchTool(BaseTool):
    name = "kg_search"
    description = (
        "在公共知识图谱（KG）中检索与给定查询相关的概念、教法切面（讲法/类比/例子）"
        "和共性反馈（易错点/常见困惑/有效讲法）。"
        "这是跨用户沉淀的集体知识，应优先于 search_nodes 用于解答前的资料准备。"
        "返回结构化 JSON：concepts / facets / subgraph。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索查询，自然语言"},
            "top_k_concepts": {
                "type": "integer",
                "description": "返回多少个相关概念（默认 5，最大 10）",
                "default": 5,
            },
            "top_k_facets_per_concept": {
                "type": "integer",
                "description": "每个概念召回多少个切面（默认 3）",
                "default": 3,
            },
        },
        "required": ["query"],
    }

    def __init__(self) -> None:
        super().__init__()

    def run(
        self,
        query: str = "",
        top_k_concepts: int = 5,
        top_k_facets_per_concept: int = 3,
        **kwargs,
    ) -> str:
        from services import kg_facade

        try:
            resp = kg_facade.retrieve(
                RetrieveRequest(
                    query=query,
                    need_facets=True,
                    top_k_facets_per_concept=top_k_facets_per_concept,
                    graph_expand=True,
                    max_subgraph_size=max(3, min(top_k_concepts, 10)) + 4,
                    anchor_max_entries=max(1, min(top_k_concepts, 10)),
                )
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("kg_search 失败 query=%s", query)
            return f"Error: kg_search 异常 {exc}"

        if resp.degraded and not resp.concepts:
            return json.dumps(
                {
                    "concepts": [],
                    "facets": [],
                    "degraded": True,
                    "reason": resp.degraded_reason,
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "concepts": [
                    {
                        "id": c.id,
                        "name": c.canonical_name,
                        "summary": c.summary,
                        "subject": c.subject,
                        "difficulty": c.difficulty,
                    }
                    for c in resp.concepts
                ],
                "facets": [
                    {
                        "concept_id": f.concept_id,
                        "kind": f.kind,
                        "content": f.content,
                        "confidence": f.confidence,
                        "support_count": f.support_count,
                    }
                    for f in resp.facets
                ],
                "subgraph": [
                    {
                        "id": n.concept.id,
                        "name": n.concept.canonical_name,
                        "is_entry": n.is_entry,
                        "via_relation": n.via_relation,
                        "via_concept_id": n.via_concept_id,
                    }
                    for n in resp.subgraph
                ],
                "degraded": resp.degraded,
            },
            ensure_ascii=False,
        )


# ============================================================
# kg.resolve — 术语 → concept_id
# ============================================================


class KGResolveTool(BaseTool):
    name = "kg_resolve"
    description = (
        "把一个术语精确链接到 KG 概念 ID（用于 kg_record_observation 时确认）。"
        "返回 JSON：{concept_id, canonical_name, match_type, score}。"
        "match_type=none 表示未找到——这时如果你认为该概念有教学价值，"
        "可考虑调 kg_propose_missing_concept 提议建档。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "term": {"type": "string", "description": "要解析的术语"},
        },
        "required": ["term"],
    }

    def run(self, term: str = "", **kwargs) -> str:
        from services import kg_facade

        try:
            items = kg_facade.resolve_terms([term], top_k=1)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("kg_resolve 失败 term=%s", term)
            return f"Error: kg_resolve 异常 {exc}"
        if not items:
            return json.dumps({"match_type": "none"}, ensure_ascii=False)
        it = items[0]
        return json.dumps(
            {
                "concept_id": it.concept_id,
                "canonical_name": it.canonical_name,
                "match_type": it.match_type,
                "score": it.score,
            },
            ensure_ascii=False,
        )


# ============================================================
# kg.propose_missing_concept — 提议 KG 中缺一个概念
# ============================================================


class KGProposeMissingConceptTool(BaseTool):
    name = "kg_propose_missing_concept"
    description = (
        "当你在教学过程中**发现 KG 中缺一个有教学价值的概念**时，提议「该收」。"
        "你只需要提供概念名 + 一句话「为什么该收」（reason_brief），"
        "**不需要也不应该提供** definition / 例子 / 前置关系 —— 这些全部由人工后续处理。"
        ""
        "该提议会被记入待审清单（pending proposal），**不会被自动 approve、不会自动建档**，"
        "等管理员人工处理。"
        ""
        "请克制使用：只在你确信该概念是独立、可教学、KG 真的没有的情况下调用。"
        "日常术语、一句话能讲清的小知识点都不要提议。"
        ""
        "返回 JSON：{status: matched|matched_pending|proposed|rejected, "
        "concept_id?, proposal_id?, reason}"
        " - matched:         KG 已有该概念，无需重复提议（reason 含 concept_id）"
        " - matched_pending: 已有同名提议在待审清单中，本次未重复创建（含 proposal_id）"
        " - proposed:        已记入待审清单（reason 含 proposal_id）"
        " - rejected:        参数不合法（空名/空理由等）"
    )
    parameters = {
        "type": "object",
        "properties": {
            "concept_name": {
                "type": "string",
                "description": "你发现的缺失概念名（自然语言原话即可，如「链式法则」）",
            },
            "reason_brief": {
                "type": "string",
                "description": (
                    "≤80 字的「为什么该收」简述，给后台审核者/建档员看。"
                    "例：「学生反复在求复合函数导数时卡住，KG 检索不到该概念」。"
                    "必须具体，不能写成「这个很重要」之类的空话。"
                ),
            },
        },
        "required": ["concept_name", "reason_brief"],
    }

    def __init__(self, user_id: str, session_id: str) -> None:
        super().__init__()
        self._user_id = user_id
        self._session_id = session_id

    def run(self, concept_name: str = "", reason_brief: str = "", **kwargs) -> str:
        from services import kg_facade

        try:
            result = kg_facade.agent_propose_missing_concept(
                user_id=self._user_id,
                session_id=self._session_id,
                concept_name=concept_name,
                reason_brief=reason_brief,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("kg_propose_missing_concept 失败 name=%s", concept_name)
            return f"Error: kg_propose_missing_concept 异常 {exc}"
        return json.dumps(result, ensure_ascii=False)


# ============================================================
# kg.record_observation — agent 主动记录对用户的观察
# ============================================================


_VALID_OBS_TYPES = sorted(OBSERVATION_TYPES)


class KGRecordObservationTool(BaseTool):
    name = "kg_record_observation"
    description = (
        "记录一条对当前用户的观察（不是知识，是行为/状态/反应的笔记）。"
        "你只需要提供概念名和观察内容，系统内部会自动解析 concept_id。"
        "跨用户累积多条同类观察后，系统会自动归纳出共性提议（pending proposal），"
        "**等管理员人工审阅后**才会反哺 KG。"
        "observation_type 必须为："
        f"{_VALID_OBS_TYPES} 之一。"
        "不要为凑数据而记录，平庸的对话不需要写观察。"
        "返回：{status: recorded|skipped, observation_id?, concept_id?, reason?}"
        "—— status=skipped 表示概念未被识别，本条未落库，"
        "可考虑后续调 kg_propose_missing_concept。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "concept": {
                "type": "string",
                "description": (
                    "观察所针对的概念名称（自然语言即可，例「梯度下降」「链式法则」）。"
                    "系统会自动在 KG 中查找匹配的概念，无需提前 resolve。"
                ),
            },
            "observation_type": {
                "type": "string",
                "enum": _VALID_OBS_TYPES,
                "description": (
                    "struggle=反复出错/卡顿; breakthrough=突然理解; "
                    "misconception=说出错误概念; effective_metaphor=某个比喻让用户秒懂; "
                    "emotional_block=畏难/抗拒/兴趣低"
                ),
            },
            "description": {
                "type": "string",
                "description": (
                    "用自然语言描述你观察到的现象，要具体。"
                    "例：「用户连续 3 次把鞍点判断为局部最优，在提示 Hessian 后纠正」。"
                    "建议 ≤ 200 字。"
                ),
            },
            "agent_confidence": {
                "type": "number",
                "description": "你对这条观察的把握 0.0-1.0（默认 0.6）",
                "default": 0.6,
            },
            "related_facet_id": {
                "type": "string",
                "description": "可选：如果这条观察验证/挑战了某条已有 facet，写 facet_id",
            },
        },
        "required": ["concept", "observation_type", "description"],
    }

    def __init__(self, user_id: str, session_id: str) -> None:
        super().__init__()
        self._user_id = user_id
        self._session_id = session_id

    def run(
        self,
        concept: str = "",
        observation_type: str = "",
        description: str = "",
        agent_confidence: float = 0.6,
        related_facet_id: str = "",
        **kwargs,
    ) -> str:
        from services import kg_facade

        if observation_type not in OBSERVATION_TYPES:
            return (
                f"Error: observation_type 非法 ({observation_type})，"
                f"必须从 {_VALID_OBS_TYPES} 中选"
            )

        try:
            result = kg_facade.agent_record_observation(
                user_id=self._user_id,
                session_id=self._session_id,
                concept=concept,
                observation_type=observation_type,
                description=description,
                agent_confidence=agent_confidence,
                related_facet_id=related_facet_id or None,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception(
                "kg_record_observation 失败 concept=%s type=%s",
                concept,
                observation_type,
            )
            return f"Error: kg_record_observation 异常 {exc}"
        return json.dumps(result, ensure_ascii=False)
