"""L2 用户画像（结构化记忆）模型。

包含四类结构：
- ProfileFactSchema：结构化事实（可审计、支持时间衰减）。
- ProfileFactCandidate：LLM 提取出的候选事实（落库前的中间结构）。
- ProfileOverviewSchema：统一画像总览（整体判断 + 兴趣/水平/知识面/行为统计）。
- ProfileSkillSchema：由 facts 编译的画像技能（按任务激活）。
- ProfileFactHistorySchema：append-only 变更流水审计。

同时提供时间衰减相关常量与 effective_confidence 纯函数辅助，
供 Repository 在读取时动态计算有效置信度（不持久化、零后台任务）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import Field

from .base import BaseSchema

# ---------------------------------------------------------------------------
# 枚举（用 Literal 表达，保持与 DDL 注释一致）
# ---------------------------------------------------------------------------

# 事实分类
FactCategory = Literal[
    "basic",  # 基础信息（年级、专业等）
    "goal",  # 学习目标
    "interest",  # 长期兴趣/偏好主题
    "ability",  # 能力水平
    "preference",  # 讲解/学习偏好
    "mistake_pattern",  # 易错点/薄弱点
    "habit",  # 学习习惯
    "interaction",  # 交互风格
    "constraints",  # 约束（时间、设备等）
]

# 证据类型（决定优先级与半衰期）
EvidenceType = Literal["explicit", "quiz", "behavior", "inference"]

# 事实状态
FactStatus = Literal["active", "archived", "superseded"]

# 变更类型
ChangeType = Literal[
    "created",
    "reinforced",
    "confidence_updated",
    "superseded",
    "archived",
]


# ---------------------------------------------------------------------------
# 时间衰减配置与计算辅助
# ---------------------------------------------------------------------------

# 证据类型 -> 优先级权重（数值化，便于冲突比较）
EVIDENCE_PRIORITY: dict[str, float] = {
    "explicit": 1.0,
    "quiz": 0.8,
    "behavior": 0.6,
    "inference": 0.4,
}

# 证据类型 -> 半衰期（天）。explicit 近似不衰减，inference 快速降权。
EVIDENCE_HALF_LIFE_DAYS: dict[str, float] = {
    "explicit": 365.0,
    "quiz": 120.0,
    "behavior": 60.0,
    "inference": 30.0,
}

# 观测晋升步长：同一事实被再次观测时 confidence 的提升量
OBSERVATION_PROMOTION_STEP = 0.1

# 惰性归档阈值：effective_confidence 跌破该值且证据类型可归档时，置 archived
DECAY_ARCHIVE_THRESHOLD = 0.2

# 允许被惰性归档的证据类型（explicit/quiz 不自动归档）
ARCHIVABLE_EVIDENCE_TYPES = {"behavior", "inference"}

# overview/skills 编译时纳入的 effective_confidence 下限
PROFILE_COMPILE_CONFIDENCE_FLOOR = 0.3


def evidence_priority(evidence_type: str) -> float:
    """返回证据类型的优先级权重，未知类型按最低 0.4 处理。"""
    return EVIDENCE_PRIORITY.get(evidence_type, 0.4)


def _parse_dt(value: str | datetime | None) -> Optional[datetime]:
    """将 ISO8601 字符串解析为带时区的 datetime；失败返回 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def effective_confidence(
    confidence: float,
    evidence_type: str,
    last_reinforced_at: str | datetime | None,
    now: datetime | None = None,
) -> float:
    """读时动态计算有效置信度。

    公式：effective = confidence * 0.5 ** (Δdays / half_life)
    其中 Δdays = now - last_reinforced_at（天），half_life 由证据类型决定。

    last_reinforced_at 无法解析时按"不衰减"处理（返回原 confidence），
    避免脏数据导致事实被错误降权。
    """
    base = _parse_dt(last_reinforced_at)
    if base is None:
        return confidence
    now = now or datetime.now(timezone.utc)
    delta_days = (now - base).total_seconds() / 86400.0
    if delta_days <= 0:
        return confidence
    half_life = EVIDENCE_HALF_LIFE_DAYS.get(evidence_type, 30.0)
    if half_life <= 0:
        return confidence
    return confidence * (0.5 ** (delta_days / half_life))


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------


class ProfileFactSchema(BaseSchema):
    """一条结构化用户事实。"""

    id: str
    user_id: str
    category: str
    key: str
    value: str
    value_type: str = "text"
    evidence_type: str
    confidence: float = 0.5
    importance: float = 0.5
    observation_count: int = 1
    source_ref: str = ""
    evidence: list = Field(default_factory=list)
    status: str = "active"
    last_reinforced_at: datetime
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ProfileFactCandidate(BaseSchema):
    """LLM 提取出的候选事实（落库前的中间结构）。"""

    category: str
    key: str
    value: str
    evidence_type: str = "inference"
    confidence: float = 0.5
    importance: float = 0.5
    evidence: list = Field(default_factory=list)
    source_ref: str = ""


class ProfileSkillSchema(BaseSchema):
    """由 facts 编译的画像技能（按任务激活）。"""

    id: str
    user_id: str
    skill_name: str
    skill_type: str = ""
    content: str
    trigger_conditions: list = Field(default_factory=list)
    source_fact_ids: list = Field(default_factory=list)
    priority: float = 0.5
    status: str = "active"
    created_at: datetime
    updated_at: datetime


class ProfileOverviewSchema(BaseSchema):
    """统一画像总览：对外读取的唯一画像入口。"""

    user_id: str
    overall_judgement: str = ""
    interests: list[str] = Field(default_factory=list)
    learning_level: str = ""
    knowledge_scope: str = ""
    dialogue_preference: str = ""
    learning_behavior: str = ""
    weakness_summary: str = ""
    strategy_summary: str = ""
    source_snapshot: dict = Field(default_factory=dict)
    facts_snapshot: list = Field(default_factory=list)
    version: int = 1
    updated_at: datetime


class ProfileFactHistorySchema(BaseSchema):
    """append-only 变更流水审计记录。"""

    id: str
    user_id: str
    fact_id: str
    category: str
    key: str
    change_type: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    old_confidence: Optional[float] = None
    new_confidence: Optional[float] = None
    evidence_type: str = ""
    source_ref: str = ""
    reason: str = ""
    created_at: datetime
