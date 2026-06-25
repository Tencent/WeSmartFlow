# KG（知识图谱子模块 · 反馈闭环版）

> 自 2026-06 重构起，KG 不再是"概念 + 展品 + 信源切块"的三段式，而是**反馈闭环模型**：
> `Concept`（稳定本体）+ `Facet`（教法 / 共性反馈切面）+ `Observation`（agent 在对话中对用户的观察流）+ `Proposal`（硬变更审核队列）。
> 同进程零序列化、零网络开销，存储完全独立（自己的 `kg.db` + 自己的 sqlite-vec `kg_vec.db`）。
> **不对外暴露 HTTP 路由**，所有调用方通过同进程 import [`backend/services/kg_facade.py`](../services/kg_facade.py) 进入。

---

## 设计取舍

- **KG 是公共的**：所有用户共享同一份 concept / facet / edge。用户态（掌握度 / SM-2 / 会话历史）**完全不进 KG**。
- **写入收敛**：所有对 concept / facet / edge 的硬变更必须先变成一条 `Proposal`，审核通过才落库（[`AutoApproveGate`](../services/kg_auto_gate.py) 决定是否自动放行）。
- **教学 Agent = 发现者 + 观察者**:它在对话中只允许两种写入动作:
  1. 「发现」`KG 中缺一个概念` → `kg_propose_missing_concept`(只提供名+理由) → 后台建档员异步生成 concept + PEDAGOGY facets + 弱关系
  2. 「观察」`对用户的学习举动` → `kg_record_observation`(concept_text + observation_type + description) → 后台聚合器跨用户归纳为 FEEDBACK facet
- **教学 Agent 不是知识工程师**:不再提供「直写 facet/edge」或「提供完整 concept 元数据」的入口。这些都是 KG 内部 ConceptBuilderService 的职责。
- **检索路径轻量**：Graph RAG 检索只跑 embedding 余弦 + 子图扩展，不引入额外 LLM 调用；LLM 仅在「聚合器归纳」/「建档员产出」/「Auto-Gate 评审」这几个写入侧触发。

---

## 模块结构

```
backend/kg/
├── __init__.py                ← 公共 API 门面（init_kg_db / Repository / Service / Models）
├── config.py                  ← 环境变量配置（KG_*）
├── database.py                ← SQLite DDL + 连接管理
├── models.py                  ← Pydantic 模型（concept / edge / facet / observation / proposal / build_queue）
├── text_for_embedding.py      ← 嵌入文本模板（concept / facet）
├── relation_semantics.py      ← 关系类型语义 probe（驱动 Graph RAG 关系打分）
├── embedder.py                ← OpenAI 兼容 embedding 客户端
├── vector_store.py            ← sqlite-vec 封装（kg_concept / kg_facet）
├── repositories/
│   ├── build_queue_repo.py     ← propose_concept_build approve 后的建档任务队列
│   ├── concept_repo.py
│   ├── edge_repo.py            ← 含 support_count（被对话印证次数）
│   ├── facet_repo.py
│   ├── observation_repo.py     ← agent 写入的对用户的观察（含分桶统计 / mark_processed）
│   └── proposal_repo.py
└── services/
    ├── retrieve_service.py        ← Graph RAG 两段式：concept 锚定 + facet 召回
    ├── proposal_service.py        ← Proposal 创建 + 审批落库（事务）
    ├── aggregator_service.py      ← observation → LLM 归纳 → add_facet Proposal
    └── concept_builder_service.py ← 从 build_queue 取任务 → LLM 生成 concept + PEDAGOGY facets + 弱关系
```

---

## 数据流

```
┌──────────────────────────────────────────────────────────────────┐
│ 用户 ↔ Agent 对话                                                 │
│   ├ 检索:           kg_facade.retrieve()                            │
│   ├ 观察轨道:        KGRecordObservationTool                          │
│   │                  → kg_facade.submit_observation                    │
│   └ 发现轨道:        KGProposeMissingConceptTool                      │
│                     → kg_facade.agent_propose_missing_concept         │
│                     → propose_concept_build proposal + AutoGate       │
│                     → 提议 approve 后入 concept_build_queue            │
└──────────────────────────────────────────────────────────────────┘
              │（异步,由 services/kg_background.py 两个周期 loop 拉动）
              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 观察轨道: AggregatorService.run_once()                              │
│   bucket by (concept_id, observation_type)                          │
│   ├ 桶大小 < per-type 阈值       ⇒ 跳过（留待下轮）                  │
│   ├ 桶大小 ≥ 阈值 → 调 LLM 归纳 ⇒                                  │
│   │     · should_propose=true   → 生成 add_facet Proposal             │
│   │                                + AutoApproveGate 审决              │
│   │     · should_propose=false  → 全部 mark_processed                 │
│   └ 已处理的观察统一 mark_processed(derived_proposal_id)             │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ 发现轨道: ConceptBuilderService.run_once()                          │
│   从 concept_build_queue 领取 pending_build,逐个建档:                │
│     1) 二次去重:向量/别名检索 → 命中则 mark_skipped              │
│     2) LLM 生成 concept 元数据 → create_concept proposal + AutoGate │
│     3) LLM 生成 PEDAGOGY facet 套件 → add_facet × N + AutoGate       │
│     4) 关系驱动 8 路向量召回 → LLM 选关系类型+方向 → 双向 add_edge   │
│     全部产出打 origin=agent_authored,待后续人工精修                  │
└──────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────┐
│ ProposalService.approve()                                          │
│   按 op 分发到 concept_repo / facet_repo / edge_repo / build_queue   │
│   【注】propose_concept_build approve 时,并不直接建 concept,         │
│        而是入 concept_build_queue 交给建档员                       │
└──────────────────────────────────────────────────────────────────┘
```
---

## 在 backend 中的使用

backend `main.py` 启动时自动调用：

```python
from kg import init_kg_db
init_kg_db()      # 幂等建表
```

业务侧统一走 [`backend/services/kg_facade.py`](../services/kg_facade.py)：

```python
from services import kg_facade
from kg import RetrieveRequest, ObservationCreate, ProposalCreate

# 1) 检索（前端 / Agent 主用）
resp = kg_facade.retrieve(RetrieveRequest(query="切线斜率与导数的几何意义"))
# resp.concepts / resp.facets / resp.subgraph / resp.weak_candidates

# 2) 实体链接：自由文本 → concept_id
items = kg_facade.resolve_terms(["导数", "微商"], top_k=1)

# 3) Agent 写一条对用户的观察（对话过程中实时调，无审核，立即落库）
kg_facade.submit_observation(
    ObservationCreate(
        concept_text="导数",
        observation_type="misconception",
        description="用户把 f'(x) 与 f(x) 混为一谈，反复在切线方程里代入函数值",
        session_id=session.id,
        user_id=user.id,
        agent_confidence=0.7,
    )
)

# 4) Agent 提议「KG 中缺一个概念」(只传名 + 理由;其余交给后台建档员)
kg_facade.agent_propose_missing_concept(
    user_id=user.id,
    session_id=session.id,
    concept_name="链式法则",
    reason_brief="多名学生在复合函数求导时卡住,但 KG 检索不到该概念",
)

# 5) 跑一次聚合 / 一次建档(实际由 services/kg_background.py 的周期 loop 自动拉动,
#    一般不需要业务侧手动调用)
kg_facade.run_aggregator_once(batch_size=200)
kg_facade.run_concept_builder_once(batch_size=5)
```

---

## 对外暴露面

KG **不暴露任何 HTTP 路由**，统一通过同进程 import 进入：

| 入口 | 调用方 | 说明 |
|---|---|---|
| `kg_facade.retrieve` | tutor_service 前置 RAG / Agent 工具 | Graph RAG 两段式检索 |
| `kg_facade.resolve_terms` | Agent 工具 / 内部 | 自由文本 → concept_id |
| `kg_facade.submit_observation` | Agent（`KGRecordObservationTool`） | 写一条对用户的观察 |
| `kg_facade.agent_propose_missing_concept` | Agent（`KGProposeMissingConceptTool`） | 提议「KG 中缺这个概念」,后台异步建档 |
| `kg_facade.submit_proposal` | 任意提议方（主要是内部脚本 / 离线任务） | 直接构造 Proposal 写队列 |
| `kg_facade.run_aggregator_once` | `services/kg_background.py` 周期 loop | 拉动观察 → FEEDBACK facet 闭环 |
| `kg_facade.run_concept_builder_once` | `services/kg_background.py` 周期 loop | 拉动 build_queue → 新 concept 建档 |
| `kg_facade.approve_proposal` / `reject_proposal` / `bulk_reject_pending` | 内部审核流程（AutoApproveGate / 离线 job） | 不直接对终端用户暴露 |

### Agent 写入面总结

教学 Agent 在对话中实际可调的写入入口只有两个:

1. `kg_record_observation` — 记录对用户的观察(后台聚合 → FEEDBACK facet)
2. `kg_propose_missing_concept` — 提议 KG 中缺一个概念(后台建档员 → concept + PEDAGOGY facets + 弱关系)

它没有「直写 facet/edge/concept 完整元数据」的入口。这些都是 KG 内部专职服务的职责,产出全部打上 `origin=agent_authored`(建档员) 或 `origin=dialog_aggregated`(聚合器) 以供后续人工精修。

---

## 关键概念词典

| 名词 | 形态 | 写入路径 | 是否进入审核 |
|---|---|---|---|
| `Concept`        | SQLite + sqlite-vec `kg_concept` | Proposal | ✅ |
| `ConceptEdge`    | SQLite                       | Proposal | ✅（带 `support_count` 软强化）|
| `Facet`          | SQLite + sqlite-vec `kg_facet`   | Proposal | ✅（带 `support_count` 软强化）|
| `Observation`    | SQLite                       | 直接落库 | ❌ agent 在对话中实时写入；聚合器消费后 `mark_processed` |
| `Proposal`       | SQLite                       | 直接落库（pending）| 审批后才执行落库 |
| `ConceptBuildQueue` | SQLite                    | propose_concept_build approve 后入队 | ❌ 后台建档员消费 |

`Facet.origin` 取值:
- `manual`            人工录入(教研老师 / 种子脚本)
- `dialog_aggregated` 由聚合器从 observation 归纳而来 (FEEDBACK 类)
- `agent_authored`    由建档员自动产出 (PEDAGOGY 类 + 新 concept + 弱关系,质量较低,待精修)
- `agent_proposed`    历史遗留(已废弃,新代码不再产生)

`Facet.layer`：
- `pedagogy`：教法层（definition / intuition / analogy / example / counter_example / derivation / visualization / teaching_strategy）
- `feedback`：共性反馈层（pitfall / confusion / effective_strategy / ineffective_strategy / prerequisite_gap）

`kind` 是**半开放枚举**：在推荐表里 → `kind_is_custom=0`；不在 → `kind_is_custom=1`，自动接受。

`Observation.observation_type`（聚合分桶维度，5 类闭集）：
- `struggle` / `breakthrough` / `misconception` / `effective_metaphor` / `emotional_block`

聚合器 `AggregatorService` 的 per-type 触发阈值见 [`aggregator_service.py`](services/aggregator_service.py) 中的 `DEFAULT_TRIGGER_THRESHOLD`。

---

## 安装

```bash
conda run -n edu-agent pip install -r backend/requirements.txt
```

关键依赖：`sqlite-vec` / `openai` / `pydantic` / `python-dotenv`（FastAPI 由 backend 提供）。

---

## 配置项（环境变量，统一放仓库根 `.env`，模板见 `backend/.env.example`）

| 变量 | 说明 | 默认 |
|---|---|---|
| `KG_DATA_DIR` | 数据根目录 | `<repo>/data` |
| `KG_DB_FILE` | KG 主库 SQLite 文件名 | `kg.db` |
| `KG_VEC_DB_FILE` | 向量库 SQLite 文件名（sqlite-vec） | `kg_vec.db` |
| `KG_VEC_DB_PATH` | 向量库完整路径（覆盖 KG_VEC_DB_FILE） | `<KG_DATA_DIR>/<KG_VEC_DB_FILE>` |
| `KG_EMBEDDING_API_KEY` | OpenAI 兼容 API key（**留空则关闭向量通道**）| — |
| `KG_EMBEDDING_BASE_URL` | OpenAI 兼容 base url | — |
| `KG_EMBEDDING_MODEL` | 模型名 | `text-embedding-v4` |
| `KG_EMBEDDING_DIM` | 向量维度 | `1024` |
| `KG_EMBEDDING_BATCH` | 单批最大条数 | `10` |
| `KG_ANCHOR_*` / `KG_REL_WEIGHT_FLOOR` / `KG_NEIGHBOR_FANOUT` | Graph RAG 调参 | 见 `config.py` |

---

## 数据目录布局

```
data/
├── kg.db              # KG 主库（concept / facet / observation / proposal …）
├── kg.db-shm
├── kg.db-wal
├── kg_vec.db          # 向量库（sqlite-vec：kg_concept / kg_facet 虚表 + vec_meta）
├── kg_vec.db-shm
└── kg_vec.db-wal
```

清空重置：

```bash
rm -rf data/kg.db* data/kg_vec.db*
```

下次 backend 启动时 `init_kg_db()` 会自动重建表结构。
