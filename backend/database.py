"""
SQLite 数据库初始化与连接管理

设计原则：
- 使用 sqlite3 标准库，零依赖
- WAL 模式提升并发读性能
- 所有表在首次启动时自动创建（如不存在）
- 对外暴露 get_db() 上下文管理器，FastAPI 依赖注入用
- DDL 始终保持最新完整结构，不包含任何兼容迁移逻辑
- 旧数据库迁移请运行 migrate_db.py
"""

import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator

import bcrypt

from config import DB_PATH

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# DDL：建表语句（最新完整结构，可直接用于全新数据库）
# --------------------------------------------------------------------------

_CREATE_TABLES_SQL = """
-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT UNIQUE,
    password_hash   TEXT NOT NULL DEFAULT '',
    avatar_url      TEXT,
    wechat_openid   TEXT UNIQUE,
    github_id       TEXT UNIQUE,
    github_username TEXT,
    preferences     TEXT NOT NULL DEFAULT '{}',
    about           TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL
);

-- 文档表（上传的 PDF/txt 或 AI 生成的课件）
CREATE TABLE IF NOT EXISTS documents (
    id                          TEXT PRIMARY KEY,
    user_id                     TEXT NOT NULL,
    title                       TEXT NOT NULL,
    source                      TEXT NOT NULL,
    file_name                   TEXT NOT NULL,
    storage_key                 TEXT NOT NULL DEFAULT '',
    file_type                   TEXT NOT NULL,
    file_size                   INTEGER NOT NULL DEFAULT 0,
    status                      TEXT NOT NULL DEFAULT 'pending',
    error_msg                   TEXT,
    total_pages                 INTEGER,
    generated_from_session_id   TEXT,
    generation_prompt           TEXT,
    node_ids                    TEXT NOT NULL DEFAULT '[]',
    created_at                  TEXT NOT NULL,
    processed_at                TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 知识节点表
CREATE TABLE IF NOT EXISTS nodes (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    tags            TEXT NOT NULL DEFAULT '[]',
    content         TEXT NOT NULL DEFAULT '{}',
    origins         TEXT NOT NULL DEFAULT '[]',
    relations       TEXT NOT NULL DEFAULT '[]',
    ease_factor     REAL NOT NULL DEFAULT 2.5,
    interval        INTEGER NOT NULL DEFAULT 1,
    repetitions     INTEGER NOT NULL DEFAULT 0,
    due_date        TEXT,
    last_review_at  TEXT,
    mastery_level   REAL NOT NULL DEFAULT 0.0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 会话表
CREATE TABLE IF NOT EXISTS sessions (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL,
    title               TEXT,
    topic               TEXT,
    status              TEXT NOT NULL DEFAULT 'active',
    node_ids_covered    TEXT NOT NULL DEFAULT '[]',
    files               TEXT NOT NULL DEFAULT '[]',
    message_count       INTEGER NOT NULL DEFAULT 0,
    duration_minutes    INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    ended_at            TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ====================================================================
-- 题目本体 与 作答记录 分离
--   question_bank —— 题目本体，唯一存放处，可被反复取用
--                    （来源：LLM 生成 / exercises.md 导入 / 人工录入）
--   quizzes       —— 一次具体的作答实例，只存「谁、在哪次会话、答了哪道题、结果如何」
--                    题干/选项/答案/解析一律通过 question_id 引用，不再冗余存储
-- ====================================================================

-- 题库表（题目本体）
CREATE TABLE IF NOT EXISTS question_bank (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    node_id         TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'llm',      -- llm / exercises_md / manual
    quiz_type       TEXT NOT NULL,
    question        TEXT NOT NULL,
    options         TEXT,
    correct_answer  TEXT NOT NULL,
    explanation     TEXT NOT NULL DEFAULT '',
    difficulty      TEXT NOT NULL DEFAULT 'medium',   -- easy / medium / hard
    use_count       INTEGER NOT NULL DEFAULT 0,
    last_used_at    TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (node_id) REFERENCES nodes(id),
    UNIQUE (user_id, node_id, question)
);
CREATE INDEX IF NOT EXISTS idx_question_bank_pick
    ON question_bank(user_id, node_id, quiz_type, use_count);

-- 作答记录表（一次作答实例）
CREATE TABLE IF NOT EXISTS quizzes (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    node_id         TEXT NOT NULL,          -- 冗余一份便于按节点索引，语义等同题目所属节点
    question_id     TEXT NOT NULL,          -- → question_bank.id，题目本体唯一来源
    session_id      TEXT,
    user_answer     TEXT,
    is_correct      INTEGER,
    score           REAL,
    answered_at     TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (node_id) REFERENCES nodes(id),
    FOREIGN KEY (question_id) REFERENCES question_bank(id)
);
CREATE INDEX IF NOT EXISTS idx_quizzes_user_node
    ON quizzes(user_id, node_id, created_at);
CREATE INDEX IF NOT EXISTS idx_quizzes_question
    ON quizzes(question_id);

-- 学习日志表（热力图 & 统计）
CREATE TABLE IF NOT EXISTS study_logs (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    date        TEXT NOT NULL,
    minutes     INTEGER NOT NULL,
    session_id  TEXT,
    node_ids    TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_study_logs_user_date ON study_logs(user_id, date);

-- 每日学习计划缓存表
CREATE TABLE IF NOT EXISTS daily_plans (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    date            TEXT NOT NULL,
    tasks           TEXT NOT NULL DEFAULT '[]',
    recommendation  TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE (user_id, date)
);

-- 每日资讯简报缓存表
CREATE TABLE IF NOT EXISTS daily_briefs (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    date        TEXT NOT NULL,
    news_groups TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE (user_id, date)
);

-- 用户设置表（每用户独立 KV 存储）
CREATE TABLE IF NOT EXISTS settings (
    user_id     TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, key),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ====================================================================
-- credits 用量体系
--
-- 按 token 与真实定价折算 credits，并保留场景/模型维度用于归因。
--
--   usage_events  —— 每次调用一条流水，可审计、可按场景归因
--   usage_summary —— 按 (user_id, period) 汇总，热路径只读这张表
--   credit_quotas —— 旧月度配额表，仅保留历史兼容，不参与余额控制
-- ====================================================================

CREATE TABLE IF NOT EXISTS usage_events (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    period            TEXT NOT NULL,              -- 'YYYY-MM'，额度重置周期
    category          TEXT NOT NULL,              -- llm / embedding / search / image / audio
    scene             TEXT NOT NULL DEFAULT 'unknown',
                                                  -- quiz/chat/immersive/profile/kg/court...
    model             TEXT NOT NULL DEFAULT '',
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    -- 思考 token：推理模型的隐式开销，单列以便评估 reasoning_effort 优化收益
    reasoning_tokens  INTEGER NOT NULL DEFAULT 0,
    -- 命中提示缓存的 token：单价通常低一个数量级，需与新鲜 token 分开计价
    cached_tokens     INTEGER NOT NULL DEFAULT 0,
    credits           INTEGER NOT NULL DEFAULT 0,
    -- 系统内部任务（用户未主动触发）不计入用户额度，但仍记账以保持成本可观测
    is_system         INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_events_user_period
    ON usage_events(user_id, period);
CREATE INDEX IF NOT EXISTS idx_usage_events_scene
    ON usage_events(period, scene);
CREATE INDEX IF NOT EXISTS idx_usage_events_created
    ON usage_events(created_at);

CREATE TABLE IF NOT EXISTS usage_details (
    event_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT '',
    region TEXT NOT NULL DEFAULT '',
    units REAL NOT NULL DEFAULT 0,
    pricing_version TEXT NOT NULL DEFAULT '',
    estimated INTEGER NOT NULL DEFAULT 0,
    counts_quota INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS usage_summary (
    user_id  TEXT NOT NULL,
    period   TEXT NOT NULL,
    credits  INTEGER NOT NULL DEFAULT 0,
    calls    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, period)
);

-- 用户 credits 配额覆盖表。
-- 旧表仅保留兼容；余额控制改用 credit_wallets。原先只有管理员
-- 为特定用户调整过额度时才落库（覆盖默认）。
CREATE TABLE IF NOT EXISTS credit_quotas (
    user_id        TEXT PRIMARY KEY,
    period_credits INTEGER NOT NULL,
    updated_by     TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

-- ====================================================================
-- L2 用户画像（结构化记忆）：facts / fact_history / overview / skills
-- ====================================================================

-- 结构化事实源（可审计，支持时间衰减）
CREATE TABLE IF NOT EXISTS user_profile_facts (
    id                 TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL,
    category           TEXT NOT NULL,          -- basic/goal/interest/ability/preference/mistake_pattern/habit/interaction/constraints
    key                TEXT NOT NULL,
    value              TEXT NOT NULL,
    value_type         TEXT NOT NULL DEFAULT 'text',
    evidence_type      TEXT NOT NULL,          -- explicit/quiz/behavior/inference（决定优先级与半衰期）
    confidence         REAL NOT NULL DEFAULT 0.5,
    importance         REAL NOT NULL DEFAULT 0.5,
    observation_count  INTEGER NOT NULL DEFAULT 1,
    source_ref         TEXT NOT NULL DEFAULT '',
    evidence           TEXT NOT NULL DEFAULT '[]',
    status             TEXT NOT NULL DEFAULT 'active', -- active/archived/superseded
    last_reinforced_at TEXT NOT NULL,          -- 衰减基准：仅新证据强化时刷新
    valid_from         TEXT,
    valid_until        TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    UNIQUE (user_id, category, key),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_profile_facts_user ON user_profile_facts(user_id, status);

-- 变更流水（append-only 审计，永不物理删除）
CREATE TABLE IF NOT EXISTS user_profile_fact_history (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    fact_id        TEXT NOT NULL,
    category       TEXT NOT NULL,
    key            TEXT NOT NULL,
    change_type    TEXT NOT NULL,              -- created/reinforced/confidence_updated/superseded/archived
    old_value      TEXT,
    new_value      TEXT,
    old_confidence REAL,
    new_confidence REAL,
    evidence_type  TEXT NOT NULL DEFAULT '',
    source_ref     TEXT NOT NULL DEFAULT '',
    reason         TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fact_history_user ON user_profile_fact_history(user_id, fact_id);

-- 由 facts 编译的画像技能（按任务激活）
CREATE TABLE IF NOT EXISTS user_profile_skills (
    id                 TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL,
    skill_name         TEXT NOT NULL,          -- explanation_style/learning_path/quiz_generation/review_schedule/interaction_style
    skill_type         TEXT NOT NULL DEFAULT '',
    content            TEXT NOT NULL,
    trigger_conditions TEXT NOT NULL DEFAULT '[]', -- JSON: 可激活 task_type 列表
    source_fact_ids    TEXT NOT NULL DEFAULT '[]',
    priority           REAL NOT NULL DEFAULT 0.5,
    status             TEXT NOT NULL DEFAULT 'active',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    UNIQUE (user_id, skill_name),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 统一画像总览（对外读取入口：整体判断 + 兴趣/水平/知识面/行为统计）
CREATE TABLE IF NOT EXISTS user_profile_overview (
    user_id             TEXT PRIMARY KEY,
    overall_judgement   TEXT NOT NULL DEFAULT '',
    interests           TEXT NOT NULL DEFAULT '[]',
    learning_level      TEXT NOT NULL DEFAULT '',
    knowledge_scope     TEXT NOT NULL DEFAULT '',
    dialogue_preference TEXT NOT NULL DEFAULT '',
    learning_behavior   TEXT NOT NULL DEFAULT '',
    weakness_summary    TEXT NOT NULL DEFAULT '',
    strategy_summary    TEXT NOT NULL DEFAULT '',
    source_snapshot     TEXT NOT NULL DEFAULT '{}',
    facts_snapshot      TEXT NOT NULL DEFAULT '[]',
    version             INTEGER NOT NULL DEFAULT 1,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 图谱视图配置：LLM 生成的派生展示视图，不改变原始节点/边事实
CREATE TABLE IF NOT EXISTS graph_view_profiles (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    view_type       TEXT NOT NULL DEFAULT 'simplified',
    name            TEXT NOT NULL DEFAULT '简化图谱',
    status          TEXT NOT NULL DEFAULT 'active',
    source_snapshot TEXT NOT NULL DEFAULT '{}',
    view_config     TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (user_id, view_type),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

# --------------------------------------------------------------------------
# 连接工厂
# --------------------------------------------------------------------------


def _make_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码是否匹配哈希；空值/损坏哈希一律视为不可用。"""
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


LEGACY_DEFAULT_PASSWORD = "123456"


def _ensure_default_user(conn: sqlite3.Connection) -> None:
    """确保外键兜底用户存在，且不携带任何可用口令。

    ``default`` 是历史匿名/示例路径固定使用的 user_id，攻击者无需猜测。
    因此该账号不能有可登录口令：新库直接写空哈希；旧库若仍是公开的
    "123456" 口令，则在启动时就地清除。
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO users (id, name, password_hash, avatar_url, preferences, created_at)
        VALUES ('default', '默认用户', '', NULL, '{}', datetime('now'))
        """
    )
    row = conn.execute("SELECT password_hash FROM users WHERE id='default'").fetchone()
    if row and row[0] and verify_password(LEGACY_DEFAULT_PASSWORD, row[0]):
        conn.execute("UPDATE users SET password_hash='' WHERE id='default'")
        logger.warning("已清除 default 用户的公开默认口令")


def init_db() -> None:
    """
    建表（幂等），应用启动时调用一次。

    注意：此函数假设数据库结构已是最新版本。
    如果是从旧版本升级，请先运行 migrate_db.py 完成迁移。
    """
    with _make_connection() as conn:
        conn.executescript(_CREATE_TABLES_SQL)
        conn.executescript(_LEARNING_MAP_SCHEMA)
        from migrate_credits import ensure_detail_columns

        ensure_detail_columns(conn)
        from services.credit_wallet import (
            SCHEMA,
            ensure_credit_card_columns,
            initialize_existing,
        )

        conn.executescript(SCHEMA)
        ensure_credit_card_columns(conn)

        # 确保默认用户存在（外键约束需要），且不带可用口令
        _ensure_default_user(conn)
        initialize_existing(conn)
        conn.commit()
    logger.info("数据库初始化完成：%s", DB_PATH)
    _init_settings_for_user("default")


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    统一的数据库连接上下文管理器（短连接模式）。

    用法：
        with get_db() as conn:
            conn.execute(...)
            # 退出 with 块时自动 commit
    """
    conn = _make_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Settings 工具函数
# --------------------------------------------------------------------------

_SETTINGS_SCHEMA: list[tuple[str, str, str, str]] = [
    # (key, env_var, description, default)
    ("llm_api_key", "LLM_API_KEY", "LLM API Key（OpenAI 兼容）", ""),
    ("llm_base_url", "LLM_BASE_URL", "LLM API Base URL（OpenAI 兼容）", ""),
    ("llm_model", "LLM_MODEL", "LLM 模型名称（OpenAI 兼容）", ""),
    ("tavily_api_key", "TAVILY_API_KEY", "Tavily Search API Key", ""),
    ("img_api_key", "IMG_API_KEY", "图像生成 API Key（OpenAI 兼容）", ""),
    ("img_base_url", "IMG_BASE_URL", "图像生成 Base URL（OpenAI 兼容）", ""),
    ("img_model", "IMG_MODEL", "图像生成模型名称（OpenAI 兼容）", ""),
]


def _init_settings_for_user(user_id: str) -> None:
    """为指定用户初始化 settings 表。"""
    with _make_connection() as conn:
        for key, _env_var, description, _default in _SETTINGS_SCHEMA:
            conn.execute(
                """
                INSERT OR IGNORE INTO settings (user_id, key, value, description, updated_at)
                VALUES (?, ?, '', ?, datetime('now'))
                """,
                (user_id, key, description),
            )
        conn.commit()
    logger.info(
        "用户 %s 的 settings 初始化完成（初始值为空，使用平台公共 Key）", user_id
    )


def ensure_user_settings(user_id: str) -> None:
    """确保指定用户的 settings 已初始化（注册新用户时调用）。"""
    _init_settings_for_user(user_id)


def get_all_settings(user_id: str) -> dict[str, str]:
    """读取指定用户的所有配置项，返回 {key: value} 字典。"""
    with _make_connection() as conn:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE user_id=?", (user_id,)
        ).fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_setting(user_id: str, key: str) -> str | None:
    """读取指定用户的单个配置项，不存在返回 None。"""
    with _make_connection() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE user_id=? AND key=?", (user_id, key)
        ).fetchone()
    return row["value"] if row else None


def set_setting(user_id: str, key: str, value: str) -> None:
    """写入指定用户的单个配置项（upsert）。"""
    with _make_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (user_id, key, value, description, updated_at)
            VALUES (?, ?, ?, COALESCE((SELECT description FROM settings WHERE user_id=? AND key=?), ''), datetime('now'))
            ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (user_id, key, value, user_id, key),
        )
        conn.commit()


def set_settings_batch(user_id: str, data: dict[str, str]) -> None:
    """批量写入指定用户的配置项（upsert）。"""
    with _make_connection() as conn:
        for key, value in data.items():
            conn.execute(
                """
                INSERT INTO settings (user_id, key, value, description, updated_at)
                VALUES (?, ?, ?, COALESCE((SELECT description FROM settings WHERE user_id=? AND key=?), ''), datetime('now'))
                ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (user_id, key, value, user_id, key),
            )
        conn.commit()


# --------------------------------------------------------------------------
# Learning Map：学生概念状态与可追溯学习证据
#
# 这些表属于主库，概念规范化层仍复用 kg.db。concept_key 当前既可指向
# 已审核 KG concept id，也可在迁移阶段使用 legacy:<node_id> 兼容旧节点。
# --------------------------------------------------------------------------
_LEARNING_MAP_SCHEMA = """
CREATE TABLE IF NOT EXISTS learner_concept_states (
    user_id                 TEXT NOT NULL,
    concept_key             TEXT NOT NULL,
    canonical_concept_id    TEXT,
    legacy_node_id          TEXT,
    discovered_at           TEXT NOT NULL,
    exposure_count          INTEGER NOT NULL DEFAULT 0,
    recall_score            REAL NOT NULL DEFAULT 0.0,
    application_score       REAL NOT NULL DEFAULT 0.0,
    explanation_score       REAL NOT NULL DEFAULT 0.0,
    transfer_score          REAL NOT NULL DEFAULT 0.0,
    mastery                 REAL NOT NULL DEFAULT 0.0,
    confidence              REAL NOT NULL DEFAULT 0.0,
    evidence_count          INTEGER NOT NULL DEFAULT 0,
    source_types            TEXT NOT NULL DEFAULT '[]',
    misconceptions          TEXT NOT NULL DEFAULT '[]',
    next_action             TEXT NOT NULL DEFAULT '',
    last_evidence_at        TEXT,
    due_at                  TEXT,
    updated_at              TEXT NOT NULL,
    PRIMARY KEY (user_id, concept_key),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_lcs_user_last_evidence
    ON learner_concept_states(user_id, last_evidence_at);
CREATE INDEX IF NOT EXISTS idx_lcs_user_legacy_node
    ON learner_concept_states(user_id, legacy_node_id);

CREATE TABLE IF NOT EXISTS learning_evidence (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL,
    concept_key         TEXT NOT NULL,
    canonical_concept_id TEXT,
    legacy_node_id      TEXT,
    source_type         TEXT NOT NULL,
    source_id           TEXT NOT NULL DEFAULT '',
    activity_type       TEXT NOT NULL,
    payload             TEXT NOT NULL DEFAULT '{}',
    score               REAL,
    assessment_method   TEXT NOT NULL DEFAULT 'rule',
    verified_by         TEXT NOT NULL DEFAULT 'system',
    created_at          TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_user_concept_created
    ON learning_evidence(user_id, concept_key, created_at);

CREATE TABLE IF NOT EXISTS legacy_node_concept_map (
    node_id                 TEXT PRIMARY KEY,
    canonical_concept_id    TEXT,
    match_type              TEXT NOT NULL DEFAULT 'legacy',
    score                   REAL NOT NULL DEFAULT 0.0,
    status                  TEXT NOT NULL DEFAULT 'unmapped',
    reviewed_at             TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_legacy_map_status
    ON legacy_node_concept_map(status, canonical_concept_id);
"""
