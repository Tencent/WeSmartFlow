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

-- 测验题目表
CREATE TABLE IF NOT EXISTS quizzes (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    node_id         TEXT NOT NULL,
    session_id      TEXT,
    quiz_type       TEXT NOT NULL,
    question        TEXT NOT NULL,
    options         TEXT,
    correct_answer  TEXT NOT NULL,
    explanation     TEXT NOT NULL DEFAULT '',
    user_answer     TEXT,
    is_correct      INTEGER,
    score           REAL,
    answered_at     TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (node_id) REFERENCES nodes(id)
);

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

-- API 使用量统计表
CREATE TABLE IF NOT EXISTS api_usage (
    user_id   TEXT NOT NULL,
    category  TEXT NOT NULL,
    count     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, category),
    FOREIGN KEY (user_id) REFERENCES users(id)
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


def _hash_password(plain: str) -> str:
    """对明文密码进行 bcrypt 哈希。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码是否匹配哈希。"""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def init_db() -> None:
    """
    建表（幂等），应用启动时调用一次。

    注意：此函数假设数据库结构已是最新版本。
    如果是从旧版本升级，请先运行 migrate_db.py 完成迁移。
    """
    with _make_connection() as conn:
        conn.executescript(_CREATE_TABLES_SQL)

        # 确保默认用户存在（外键约束需要）
        default_hash = _hash_password("123456")
        conn.execute(
            """
            INSERT OR IGNORE INTO users (id, name, password_hash, avatar_url, preferences, created_at)
            VALUES ('default', '默认用户', ?, NULL, '{}', datetime('now'))
            """,
            (default_hash,),
        )
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
