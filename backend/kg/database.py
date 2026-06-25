"""
KG 服务的数据库初始化与连接管理（反馈闭环版）

设计要点：
- 独立 SQLite 数据库 `data/kg.db`，不与 edu-agent 主库共用
- 使用 sqlite3 标准库，零依赖
- WAL 模式提升并发读性能
- 启动时幂等建表
- 向量检索由 sqlite-vec 承担，本表只保存 embedding_model + 向量主键

表结构：
- concept           概念节点（本体层）
- concept_edge      概念关系（带反馈强化字段）
- facet             切面（教法 + 共性反馈合一）
- observation       agent 主动记录的对用户的观察（行为/状态/反应，非知识）
- proposal          KG 硬变更的统一审核入口
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from typing import Generator

from .config import KG_DB_PATH

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# DDL：建表语句（幂等，全新数据库可直接使用）
# --------------------------------------------------------------------------

_CREATE_TABLES_SQL = """
-- 概念节点：稳定本体，低频更新
CREATE TABLE IF NOT EXISTS concept (
    id              TEXT PRIMARY KEY,
    slug            TEXT UNIQUE NOT NULL,
    canonical_name  TEXT NOT NULL,
    aliases         TEXT NOT NULL DEFAULT '[]',          -- JSON: [{"name":"...","lang":"zh"}]
    summary         TEXT NOT NULL DEFAULT '',            -- ≤80字一句话定义
    subject         TEXT NOT NULL DEFAULT '',
    difficulty      INTEGER NOT NULL DEFAULT 3 CHECK (difficulty BETWEEN 0 AND 5),

    status          TEXT NOT NULL DEFAULT 'pending',     -- pending|approved|hidden|deprecated
    merged_into_id  TEXT,

    tags            TEXT NOT NULL DEFAULT '[]',

    embedding_model TEXT NOT NULL DEFAULT '',
    vector_id       TEXT NOT NULL DEFAULT '',

    -- 增量同步用：仅 OKF 通路写入（=源 .md 整文件 sha256），
    -- 其它 origin 留空字符串。详见 ingest_okf 中的 _file_hash。
    source_hash     TEXT NOT NULL DEFAULT '',

    created_by      TEXT NOT NULL DEFAULT '',
    updated_by      TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (merged_into_id) REFERENCES concept(id)
);
CREATE INDEX IF NOT EXISTS idx_concept_status   ON concept(status);
CREATE INDEX IF NOT EXISTS idx_concept_subject  ON concept(subject);

-- 概念关系：类型化有向边（带反馈强化字段）
CREATE TABLE IF NOT EXISTS concept_edge (
    id              TEXT PRIMARY KEY,
    src_id          TEXT NOT NULL,
    dst_id          TEXT NOT NULL,
    relation_type   TEXT NOT NULL,
    weight          REAL NOT NULL DEFAULT 1.0 CHECK (weight BETWEEN 0 AND 1),
    status          TEXT NOT NULL DEFAULT 'approved',    -- proposed|approved|hidden
    support_count   INTEGER NOT NULL DEFAULT 0,          -- 被对话印证次数
    origin          TEXT NOT NULL DEFAULT 'manual',      -- manual|agent_proposed|dialog_aggregated
    origin_ref      TEXT NOT NULL DEFAULT '{}',          -- JSON {session_ids:[], message_ids:[], proposer:""}
    created_by      TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    UNIQUE (src_id, dst_id, relation_type),
    CHECK (src_id <> dst_id),
    FOREIGN KEY (src_id) REFERENCES concept(id) ON DELETE RESTRICT,
    FOREIGN KEY (dst_id) REFERENCES concept(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_edge_src   ON concept_edge(src_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_edge_dst   ON concept_edge(dst_id, relation_type);

-- 切面：挂在 concept 下的可独立检索内容单元
-- kind 完全自由文本（OKF: H1 标题 / 飞轮: LLM 生成 1-3 词标签）
-- 数据来源由 origin 区分: okf | dialog_aggregated | agent_authored | manual
CREATE TABLE IF NOT EXISTS facet (
    id                  TEXT PRIMARY KEY,
    concept_id          TEXT NOT NULL,
    kind                TEXT NOT NULL,                  -- 自由文本
    content             TEXT NOT NULL,
    extra               TEXT NOT NULL DEFAULT '{}',     -- JSON：图片/公式/document_id 等
    status              TEXT NOT NULL DEFAULT 'active', -- proposed|active|archived
    confidence          REAL NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    support_count       INTEGER NOT NULL DEFAULT 0,     -- 被印证次数（共性强度）
    first_seen_at       TEXT NOT NULL,
    last_seen_at        TEXT NOT NULL,
    origin              TEXT NOT NULL DEFAULT 'manual', -- okf|manual|dialog_aggregated|agent_authored
    origin_ref          TEXT NOT NULL DEFAULT '{}',     -- JSON：source_path / session_ids / observation_ids 等

    embedding_model     TEXT NOT NULL DEFAULT '',
    vector_id           TEXT NOT NULL DEFAULT '',

    created_by          TEXT NOT NULL DEFAULT '',
    updated_by          TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (concept_id) REFERENCES concept(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_facet_concept    ON facet(concept_id);
CREATE INDEX IF NOT EXISTS idx_facet_kind       ON facet(kind);
CREATE INDEX IF NOT EXISTS idx_facet_origin     ON facet(origin);
CREATE INDEX IF NOT EXISTS idx_facet_status     ON facet(status);

-- Observation：agent 主动记录的对用户的观察
-- 注意：这里存的是"行为/状态/反应"的笔记，不是知识本身
-- 聚合器按 (concept_id, observation_type) 分桶后用 LLM 归纳出教学知识 → Proposal → Facet
CREATE TABLE IF NOT EXISTS observation (
    id                  TEXT PRIMARY KEY,
    concept_id          TEXT NOT NULL,
    observation_type    TEXT NOT NULL,
        -- struggle | breakthrough | misconception | effective_metaphor | emotional_block
    description         TEXT NOT NULL,
    user_id             TEXT NOT NULL DEFAULT '',
    session_id          TEXT NOT NULL DEFAULT '',
    related_facet_id    TEXT,
    user_state_snapshot TEXT NOT NULL DEFAULT '{}',  -- JSON
    evidence            TEXT NOT NULL DEFAULT '{}',  -- JSON：对话片段
    agent_confidence    REAL NOT NULL DEFAULT 0.5,
    processed_at        TEXT,
    derived_proposal_id TEXT,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (concept_id) REFERENCES concept(id) ON DELETE CASCADE,
    FOREIGN KEY (related_facet_id) REFERENCES facet(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_bucket    ON observation(concept_id, observation_type, processed_at);
CREATE INDEX IF NOT EXISTS idx_obs_session   ON observation(session_id);
CREATE INDEX IF NOT EXISTS idx_obs_user      ON observation(user_id);

-- 提议：外部发起、需要审核才能进 KG 的轻提议。
-- 当前受理两种 op，两种都永远停在 pending、由人工处理：
--   * suggest_missing_concept  教学 Agent 提议「KG 中缺一个概念」
--   * suggest_facet_pattern    Aggregator 从 observations 归纳出共性 → 提议「这是个 facet」
-- 内部组件（AggregatorService）不再直写真表，而是产 proposal 等人工 approve。
CREATE TABLE IF NOT EXISTS proposal (
    id                  TEXT PRIMARY KEY,
    op                  TEXT NOT NULL,
        -- suggest_missing_concept | suggest_facet_pattern
    proposer            TEXT NOT NULL,
    payload             TEXT NOT NULL DEFAULT '{}',
    target_concept_id   TEXT,
    target_facet_id     TEXT,
    target_edge_id      TEXT,
    session_id          TEXT,
    evidence            TEXT NOT NULL DEFAULT '{}',
    status              TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|superseded
    reviewer_id         TEXT NOT NULL DEFAULT '',
    review_note         TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    reviewed_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_proposal_status ON proposal(status, created_at);
CREATE INDEX IF NOT EXISTS idx_proposal_op     ON proposal(op);
"""

# --------------------------------------------------------------------------
# 连接工厂
# --------------------------------------------------------------------------


def _make_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(KG_DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_kg_db() -> None:
    """KG 服务建表（幂等），应用启动时调用一次。"""
    with _make_connection() as conn:
        conn.executescript(_CREATE_TABLES_SQL)

        # 老库兼容：source_hash 是后加字段，存在旧 concept 表时手动 ALTER
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(concept)").fetchall()]
            if "source_hash" not in cols:
                conn.execute(
                    "ALTER TABLE concept "
                    "ADD COLUMN source_hash TEXT NOT NULL DEFAULT ''"
                )
        except Exception:  # pylint: disable=broad-except
            logger.exception("检查/补加 concept.source_hash 列失败，忽略继续")

        # 老库清理：如果老库还有 concept_build_queue 表，保留不动（不再读写），
        # 避免启动时丢失历史记录。如需彻底删除请手动迁移。

        conn.commit()
    logger.info("KG 数据库初始化完成：%s", KG_DB_PATH)


@contextmanager
def get_kg_db() -> Generator[sqlite3.Connection, None, None]:
    """统一的 KG 连接上下文管理器（短连接模式）。"""
    conn = _make_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
