"""
SQLite 数据库初始化与连接管理

设计原则：
- 使用 sqlite3 标准库，零依赖
- WAL 模式提升并发读性能
- 所有表在首次启动时自动创建（如不存在）
- 对外暴露 get_db() 上下文管理器，FastAPI 依赖注入用
"""

import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator

from config import DB_PATH

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# DDL：建表语句
# --------------------------------------------------------------------------

_CREATE_TABLES_SQL = """
-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    avatar_url  TEXT,
    preferences TEXT NOT NULL DEFAULT '{}',
    about       TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);

-- 文档表（上传的 PDF/txt 或 AI 生成的课件）
CREATE TABLE IF NOT EXISTS documents (
    id                          TEXT PRIMARY KEY,
    user_id                     TEXT NOT NULL,
    title                       TEXT NOT NULL,
    source                      TEXT NOT NULL,      -- 'uploaded' | 'generated'
    file_name                   TEXT NOT NULL,      -- 文件名（不含路径）
    file_type                   TEXT NOT NULL,      -- 'pdf' | 'txt' | 'md' | 'docx'
    file_size                   INTEGER NOT NULL DEFAULT 0,
    status                      TEXT NOT NULL DEFAULT 'pending',
    error_msg                   TEXT,
    total_pages                 INTEGER,
    generated_from_session_id   TEXT,
    generation_prompt           TEXT,               -- AI生成提示词
    generation_context          TEXT,               -- AI生成上下文
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
    messages_file       TEXT NOT NULL,
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
    quiz_type       TEXT NOT NULL,  -- 'multiple_choice' | 'fill_in' | 'true_false' | 'open_ended'
    question        TEXT NOT NULL,
    options         TEXT,           -- JSON array | null
    correct_answer  TEXT NOT NULL,
    explanation     TEXT NOT NULL DEFAULT '',
    user_answer     TEXT,
    is_correct      INTEGER,        -- 0 | 1 | null
    score           REAL,           -- 0.0~1.0，主观题 AI 评分
    answered_at     TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (node_id) REFERENCES nodes(id)
);

-- 学习日志表（热力图 & 统计）
CREATE TABLE IF NOT EXISTS study_logs (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    date        TEXT NOT NULL,      -- YYYY-MM-DD
    minutes     INTEGER NOT NULL,
    session_id  TEXT,
    node_ids    TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_study_logs_user_date ON study_logs(user_id, date);

-- 每日学习计划缓存表（AI 生成的任务 + 推荐，供 Dashboard 使用，每天只生成一次）
CREATE TABLE IF NOT EXISTS daily_plans (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    date            TEXT NOT NULL,      -- YYYY-MM-DD
    tasks           TEXT NOT NULL DEFAULT '[]',   -- JSON: DailyTask[]
    recommendation  TEXT NOT NULL DEFAULT '{}',   -- JSON: AiRecommendation
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_plans_user_date ON daily_plans(user_id, date);

-- 每日资讯简报缓存表（AI 根据 interests 生成的资讯分组，供简报页使用，每天只生成一次）
CREATE TABLE IF NOT EXISTS daily_briefs (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    date        TEXT NOT NULL,          -- YYYY-MM-DD
    news_groups TEXT NOT NULL DEFAULT '[]',   -- JSON: NewsGroup[]
    created_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_briefs_user_date ON daily_briefs(user_id, date);

-- 系统设置表（KV 存储，支持运行时修改 LLM 等配置）
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# --------------------------------------------------------------------------
# 连接工厂
# --------------------------------------------------------------------------


def _make_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row  # 结果以字典方式访问
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    """建表（幂等），应用启动时调用一次。"""
    with _make_connection() as conn:
        conn.executescript(_CREATE_TABLES_SQL)
        # 确保默认用户存在（外键约束需要）
        conn.execute(
            """
            INSERT OR IGNORE INTO users (id, name, avatar_url, preferences, created_at)
            VALUES ('default', '默认用户', NULL, '{}', datetime('now'))
            """
        )
        conn.commit()
    logger.info("数据库初始化完成：%s", DB_PATH)
    _init_settings_from_env()


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    上下文管理器，用于 FastAPI 依赖注入：

        async def route(db: sqlite3.Connection = Depends(get_db_dep)):
            ...

    每次请求获取一个独立连接，请求结束后自动提交/回滚并关闭。
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


def get_db_dep():
    """FastAPI Depends 包装器。"""
    with get_db() as conn:
        yield conn


# --------------------------------------------------------------------------
# Settings 工具函数
# --------------------------------------------------------------------------

# 所有支持的配置项定义：key -> (env_var, description, default)
_SETTINGS_SCHEMA: list[tuple[str, str, str, str]] = [
    # (key, env_var, description, default)
    ("llm_api_key", "LLM_API_KEY", "LLM API Key", ""),
    ("llm_base_url", "LLM_BASE_URL", "LLM API Base URL", ""),
    ("llm_model", "LLM_MODEL", "LLM 模型名称", ""),
    ("tavily_api_key", "TAVILY_API_KEY", "Tavily Search API Key", ""),
    ("img_api_key", "IMG_API_KEY", "图像生成 API Key", ""),
    ("img_base_url", "IMG_BASE_URL", "图像生成 Base URL", ""),
    ("img_model", "IMG_MODEL", "图像生成模型名称", ""),
]


def _init_settings_from_env() -> None:
    """将环境变量中的配置作为初始默认值写入 settings 表。
    策略：
    - key 不存在时：直接插入（无论环境变量是否为空）
    - key 已存在但值为空，且环境变量有值时：用环境变量值覆盖
    - key 已存在且值非空时：保留已有值，不覆盖
    """
    import os

    with _make_connection() as conn:
        for key, env_var, description, default in _SETTINGS_SCHEMA:
            env_value = os.getenv(env_var, default)
            # 先尝试插入（key 不存在时生效）
            conn.execute(
                """
                INSERT OR IGNORE INTO settings (key, value, description, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (key, env_value, description),
            )
            # 若 key 已存在但数据库中值为空，且环境变量有值，则用环境变量值补充
            if env_value:
                conn.execute(
                    """
                    UPDATE settings SET value=?, updated_at=datetime('now')
                    WHERE key=? AND (value IS NULL OR value='')
                    """,
                    (env_value, key),
                )
        conn.commit()
    logger.info("settings 表初始化完成（已从环境变量导入默认值）")


def get_all_settings() -> dict[str, str]:
    """读取所有配置项，返回 {key: value} 字典。"""
    with _make_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_setting(key: str) -> str | None:
    """读取单个配置项，不存在返回 None。"""
    with _make_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    """写入单个配置项（upsert）。"""
    with _make_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value, description, updated_at)
            VALUES (?, ?, COALESCE((SELECT description FROM settings WHERE key=?), ''), datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, value, key),
        )
        conn.commit()


def set_settings_batch(data: dict[str, str]) -> None:
    """批量写入配置项（upsert）。"""
    with _make_connection() as conn:
        for key, value in data.items():
            conn.execute(
                """
                INSERT INTO settings (key, value, description, updated_at)
                VALUES (?, ?, COALESCE((SELECT description FROM settings WHERE key=?), ''), datetime('now'))
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, key),
            )
        conn.commit()
