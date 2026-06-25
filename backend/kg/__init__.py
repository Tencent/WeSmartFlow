"""
KG 子模块对外门面（反馈闭环版）

KG 不再独立运行 HTTP 服务，作为 backend 的内嵌库使用。

backend 启动时调用 ``init_kg_db()`` 完成 SQLite 建表 + 预热；
业务代码统一通过 ``backend/services/kg_facade.py`` 调用本模块的能力。

公共 API：
- ``init_kg_db()``                启动时建表（幂等）
- 检索：
  - ``RetrieveService``           Graph RAG 两段式（concept + facet）
- 仓储：
  - ``ConceptRepository``
  - ``ConceptEdgeRepository``
  - ``FacetRepository``           切面（教法 + 共性反馈）
  - ``ObservationRepository``     agent 主动写入的对用户的观察
  - ``ProposalRepository``        KG 硬变更审核队列
- 服务：
  - ``ProposalService``           Proposal 创建 + 审核落库
  - ``AggregatorService``         observation → KG 反馈闭环（LLM 归纳）
- 全部 Pydantic 模型

存储：
- ``data/kg.db``      KG 主库（concept / facet / observation / proposal …）
- ``data/kg_vec.db``  向量库（sqlite-vec，单文件 + WAL，多进程友好）
"""

from __future__ import annotations

from .database import get_kg_db, init_kg_db
from .models import (
    ConceptAlias,
    ConceptBrief,
    ConceptCreate,
    ConceptEdgeCreate,
    ConceptEdgeSchema,
    ConceptResolveItem,
    ConceptResolveRequest,
    ConceptResolveResponse,
    ConceptSchema,
    ConceptUpdate,
    FacetBrief,
    FacetCreate,
    FacetSchema,
    FacetUpdate,
    OBSERVATION_TYPES,
    ObservationCreate,
    ObservationSchema,
    PROPOSAL_OPS,
    ProposalCreate,
    ProposalReview,
    ProposalSchema,
    RetrieveRequest,
    RetrieveResponse,
    SubgraphConcept,
    VALID_RELATION_TYPES,
)
from .repositories import (
    ConceptEdgeRepository,
    ConceptRepository,
    FacetRepository,
    ObservationRepository,
    ProposalRepository,
)
from .services import (
    AggregatorService,
    ProposalService,
    RetrieveService,
)

__all__ = [
    # 生命周期
    "init_kg_db",
    "get_kg_db",
    # repositories
    "ConceptRepository",
    "ConceptEdgeRepository",
    "FacetRepository",
    "ObservationRepository",
    "ProposalRepository",
    # services
    "RetrieveService",
    "ProposalService",
    "AggregatorService",
    # models
    "ConceptAlias",
    "ConceptBrief",
    "ConceptCreate",
    "ConceptEdgeCreate",
    "ConceptEdgeSchema",
    "ConceptResolveItem",
    "ConceptResolveRequest",
    "ConceptResolveResponse",
    "ConceptSchema",
    "ConceptUpdate",
    "FacetBrief",
    "FacetCreate",
    "FacetSchema",
    "FacetUpdate",
    "ObservationCreate",
    "ObservationSchema",
    "ProposalCreate",
    "ProposalReview",
    "ProposalSchema",
    "RetrieveRequest",
    "RetrieveResponse",
    "SubgraphConcept",
    # 常量
    "OBSERVATION_TYPES",
    "PROPOSAL_OPS",
    "VALID_RELATION_TYPES",
]
