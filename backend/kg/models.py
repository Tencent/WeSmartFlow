"""
KG Pydantic 模型（反馈闭环版）

层次：
- Concept / ConceptEdge：稳定本体（低频更新）
- Facet：切面层，挂在 concept 下（教法 pedagogy + 共性反馈 feedback）
- Observation：对话过程中 agent 主动记录的对用户的观察（行为/状态/反应），
  本身不是知识，由聚合器跨用户归纳后才上升为 Facet。
- Proposal：所有"硬变更"（新增/修改/合并/下线）的统一审核入口

旧的 Exhibit / Source / Chunk 三层已退役。
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Concept
# ============================================================


class ConceptAlias(_Base):
    name: str
    lang: str = "zh"


class ConceptCreate(_Base):
    # 可选: 由调用方派生稳定 id 后传入 (例如 OKF 通路用 derive_concept_id);
    # 不传则 repo 内部用 new_id() 生成 UUID (飞轮通路)。
    id: Optional[str] = None
    slug: str = Field(..., description="URL 友好的全局唯一标识")
    canonical_name: str
    aliases: list[ConceptAlias] = Field(default_factory=list)
    summary: str = ""  # ≤80字一句话定义
    subject: str = ""
    difficulty: int = 3
    status: str = "pending"
    tags: list[str] = Field(default_factory=list)
    # 增量同步专用：OKF 通路传 .md 整文件 sha256，其它通路留空。
    source_hash: str = ""
    created_by: str = ""


class ConceptUpdate(_Base):
    canonical_name: Optional[str] = None
    aliases: Optional[list[ConceptAlias]] = None
    summary: Optional[str] = None
    subject: Optional[str] = None
    difficulty: Optional[int] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None
    source_hash: Optional[str] = None
    updated_by: Optional[str] = None


class ConceptSchema(_Base):
    id: str
    slug: str
    canonical_name: str
    aliases: list[ConceptAlias] = Field(default_factory=list)
    summary: str = ""
    subject: str = ""
    difficulty: int = 3
    status: str = "pending"
    tags: list[str] = Field(default_factory=list)
    merged_into_id: Optional[str] = None
    embedding_model: str = ""
    vector_id: str = ""
    source_hash: str = ""
    created_by: str = ""
    updated_by: str = ""
    created_at: str
    updated_at: str


class ConceptBrief(_Base):
    """轻量视图，列表/邻居/检索返回时用。"""

    id: str
    slug: str
    canonical_name: str
    summary: str = ""
    subject: str = ""
    difficulty: int = 3


class ConceptResolveItem(_Base):
    """实体链接的单条结果。"""

    term: str
    concept_id: Optional[str] = None
    slug: Optional[str] = None
    canonical_name: Optional[str] = None
    score: float = 0.0
    match_type: str = "none"  # exact | alias | vector | none


class ConceptResolveRequest(_Base):
    terms: list[str]
    subject_hint: Optional[str] = None
    top_k: int = 1


class ConceptResolveResponse(_Base):
    results: list[ConceptResolveItem]


# ============================================================
# ConceptEdge
# ============================================================


VALID_RELATION_TYPES = {
    "prerequisite",
    "part_of",
    "related",
    "contrasts",
    "application_of",
    "special_case_of",
    "generalizes",
    "equivalent_to",
}


class ConceptEdgeCreate(_Base):
    # 可选: 由调用方派生稳定 id 后传入 (例如 OKF 通路用 derive_edge_id);
    # 不传则 repo 内部用 new_id() 生成 UUID。
    id: Optional[str] = None
    src_id: str
    dst_id: str
    relation_type: str
    weight: float = 1.0
    status: str = "approved"
    origin: str = "manual"  # manual | agent_proposed | dialog_aggregated
    origin_ref: dict[str, Any] = Field(default_factory=dict)
    created_by: str = ""


class ConceptEdgeSchema(_Base):
    id: str
    src_id: str
    dst_id: str
    relation_type: str
    weight: float
    status: str
    support_count: int = 0
    origin: str = "manual"
    origin_ref: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: str


# ============================================================
# Facet（切面层）
# ============================================================
#
# 重构后说明:
#   - 不再区分 layer (pedagogy/feedback)，所有 facet 平铺。
#   - kind 完全自由文本：OKF ingester 直接用 H1 标题；
#     dialog_aggregator 由 LLM 自由生成 1-3 词标签。
#   - 数据来源由 origin 字段区分:
#       okf                来自 OKF Bundle 的 ingest
#       dialog_aggregated  AggregatorService 从 observation 聚合
#                          (经管理员 approve suggest_facet_pattern 后由 ProposalService 落库)
#       manual             人工录入


class FacetCreate(_Base):
    # 可选: 由调用方派生稳定 id 后传入 (例如 OKF 通路用 derive_facet_id);
    # 不传则 repo 内部用 new_id() 生成 UUID (飞轮通路)。
    id: Optional[str] = None
    concept_id: str
    kind: str
    content: str
    extra: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.5
    origin: str = "manual"
    origin_ref: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"  # proposed | active | archived
    created_by: str = ""


class FacetUpdate(_Base):
    kind: Optional[str] = None
    content: Optional[str] = None
    extra: Optional[dict[str, Any]] = None
    confidence: Optional[float] = None
    status: Optional[str] = None
    updated_by: Optional[str] = None


class FacetSchema(_Base):
    id: str
    concept_id: str
    kind: str
    content: str
    extra: dict[str, Any] = Field(default_factory=dict)
    status: str
    confidence: float = 0.5
    support_count: int = 0
    first_seen_at: str
    last_seen_at: str
    origin: str = "manual"
    origin_ref: dict[str, Any] = Field(default_factory=dict)
    embedding_model: str = ""
    vector_id: str = ""
    created_by: str = ""
    updated_by: str = ""
    created_at: str
    updated_at: str


class FacetBrief(_Base):
    """检索结果中的 facet 摘要。"""

    id: str
    concept_id: str
    kind: str
    content: str
    confidence: float = 0.5
    support_count: int = 0
    score: float = 0.0  # 检索时的相关度分


# ============================================================
# Observation（agent 主动记录的对用户的观察，非知识本身）
# ============================================================

# 观察类型枚举：决定聚合分桶 + LLM 归纳方向
OBSERVATION_TYPES = {
    "struggle",  # 用户在该概念上反复卡壳/出错
    "breakthrough",  # 用户突然理解（错→对、能讲清楚）
    "misconception",  # 用户明确说出一个错误的概念理解
    "effective_metaphor",  # 某个比喻/类比让用户秒懂
    "emotional_block",  # 畏难、抗拒、兴趣低
}

# 注意: 观察聚合产出 facet 时, kind 由 LLM 自由生成 (1-3 词中文标签),
# 不再用硬编码映射。


class ObservationCreate(_Base):
    concept_id: str
    observation_type: str  # OBSERVATION_TYPES 之一
    description: str  # agent 用自然语言写的观察笔记

    user_id: str = ""
    session_id: str = ""

    related_facet_id: Optional[str] = None  # 观察是否针对某条已有 facet
    user_state_snapshot: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    agent_confidence: float = 0.5


class ObservationSchema(_Base):
    id: str
    concept_id: str
    observation_type: str
    description: str
    user_id: str
    session_id: str
    related_facet_id: Optional[str] = None
    user_state_snapshot: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    agent_confidence: float = 0.5
    processed_at: Optional[str] = None
    derived_proposal_id: Optional[str] = None
    created_at: str


# ============================================================
# Proposal（KG 硬变更统一入口）
# ============================================================


# op 取值（最小形态）：
# Proposal 表只承载**两种轻量信号**，两种都永远停在 pending，由管理员人工处理：
#   - suggest_missing_concept  教学 Agent 在对话中发现 KG 缺概念 → 提议「该收一个」
#                              payload: {concept_name, reason_brief}
#   - suggest_facet_pattern    AggregatorService 从一桶 observations 归纳出共性 → 提议「这是个 facet」
#                              payload: {concept_id, kind, content, observation_ids,
#                                        observation_type, rationale}
#
# 这两种 op 都不会被任何后台流程「自动 approve」。它们只是给管理员看的清单。
# 内部组件（AggregatorService / 离线脚本）对 KG 真表的「新增/修改/合并/下线」一律不再走本表，
# 而是先产 proposal、由人工 approve 后再由 ProposalService 落库。
PROPOSAL_OPS = {
    "suggest_missing_concept",
    "suggest_facet_pattern",
}


# Facet / Edge 的 origin 取值（语义化,不强制枚举校验,便于未来扩展）:
#   - manual            人工录入(教研老师 / 种子脚本)
#   - dialog_aggregated 由 AggregatorService 从 observation 聚合,
#                       管理员人工 approve suggest_facet_pattern 后由 ProposalService 落库


class ProposalCreate(_Base):
    op: str
    proposer: str  # user:xxx / agent:dialog_aggregator / agent:manual_call
    payload: dict[str, Any] = Field(default_factory=dict)
    target_concept_id: Optional[str] = None
    target_facet_id: Optional[str] = None
    target_edge_id: Optional[str] = None
    session_id: Optional[str] = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class ProposalReview(_Base):
    decision: str  # approved | rejected
    reviewer_id: str
    review_note: str = ""


class ProposalSchema(_Base):
    id: str
    op: str
    proposer: str
    payload: dict[str, Any] = Field(default_factory=dict)
    target_concept_id: Optional[str] = None
    target_facet_id: Optional[str] = None
    target_edge_id: Optional[str] = None
    session_id: Optional[str] = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    status: str  # pending | approved | rejected | superseded
    reviewer_id: str = ""
    review_note: str = ""
    created_at: str
    reviewed_at: Optional[str] = None


# ============================================================
# 检索接口
# ============================================================


class RetrieveRequest(_Base):
    query: str
    # facet 选择
    need_facets: bool = True
    facet_kinds: list[str] = Field(default_factory=list)  # 限定 kind；空=全部
    top_k_facets_per_concept: int = 4
    # Graph RAG 控制参数
    graph_expand: bool = True
    expand_hops: int = 1
    max_subgraph_size: int = 12
    # 入口锚定阈值覆盖
    anchor_min_score: Optional[float] = None
    anchor_max_entries: Optional[int] = None


class SubgraphConcept(_Base):
    """子图中的一个概念。"""

    concept: ConceptBrief
    is_entry: bool = False
    via_relation: str = ""
    via_concept_id: str = ""
    score: float = 0.0


class RetrieveResponse(_Base):
    concepts: list[ConceptBrief] = Field(default_factory=list)
    facets: list[FacetBrief] = Field(default_factory=list)
    # —— Graph RAG 调试/可解释字段 ——
    subgraph: list[SubgraphConcept] = Field(default_factory=list)
    relation_weights: dict[str, float] = Field(default_factory=dict)
    relation_dist: dict[str, float] = Field(default_factory=dict)
    # —— 弱候选 / 退化原因 ——
    weak_candidates: list[ConceptBrief] = Field(default_factory=list)
    degraded: bool = False
    degraded_reason: str = ""
