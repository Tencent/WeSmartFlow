"""
UserService：用户与 Dashboard 的业务逻辑层。

把原本散落在 ``routers/quiz_user.py`` 里 dashboard 端点的拼装逻辑下沉到此处，
让 router 层回归"参数校验 + 调用 service"的薄壳。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from models.user import DashboardStats, StudyLogSchema
from repositories import NodeRepository, SessionRepository, UserRepository
from repositories.quiz_repo import StudyLogRepository
from services.daily_plan_service import DailyPlanService

logger = logging.getLogger(__name__)


class UserService:
    """用户基础信息 & Dashboard 聚合服务。"""

    def __init__(self):
        self.user_repo = UserRepository()
        self.node_repo = NodeRepository()
        self.session_repo = SessionRepository()
        self.study_log_repo = StudyLogRepository()

    # ------------------------------------------------------------------
    # 用户基础信息
    # ------------------------------------------------------------------

    def get_user(self, user_id: str):
        """获取当前用户基本信息，找不到时返回 None（router 层负责映射 401）。"""
        return self.user_repo.get_by_id(user_id)

    def update_user(
        self,
        user_id: str,
        *,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        preferences: Any = None,
        about: Optional[str] = None,
    ):
        """更新用户基本信息（昵称、头像、偏好、个性化描述）。"""
        result = self.user_repo.update(
            user_id,
            name=name,
            avatar_url=avatar_url,
            preferences=preferences,
            about=about,
        )
        # 用户自填信息直接同步到统一画像 facts，供后续 overview 编译/注入使用。
        if about is not None or preferences is not None:
            try:
                self._sync_user_info_to_profile(
                    user_id, about=about, preferences=preferences
                )
            except Exception as e:
                logger.warning("同步用户信息到统一画像失败: %s", e)
        return result

    def _sync_user_info_to_profile(
        self, user_id: str, *, about=None, preferences=None
    ) -> None:
        """将用户自填信息同步为统一画像 facts，支持新增、修改和清空。"""
        from repositories import ProfileFactRepository, ProfileOverviewRepository

        fact_repo = ProfileFactRepository()

        def sync_text_fact(
            *,
            category: str,
            key: str,
            value: str,
            confidence: float,
            importance: float,
        ) -> None:
            value = (value or "").strip()
            if value:
                fact_repo.upsert_candidate(
                    user_id,
                    category=category,
                    key=key,
                    value=value,
                    evidence_type="explicit",
                    confidence=confidence,
                    importance=importance,
                    source_ref="user_about",
                )
            else:
                fact_repo.archive_fact(
                    user_id,
                    category,
                    key,
                    source_ref="user_about",
                    reason="user_about_cleared",
                )

        if about is not None:
            sync_text_fact(
                category="basic",
                key="self_reported_background",
                value=getattr(about, "background", ""),
                confidence=1.0,
                importance=0.8,
            )
            sync_text_fact(
                category="goal",
                key="self_reported_goals",
                value=getattr(about, "goals", ""),
                confidence=1.0,
                importance=0.9,
            )
            sync_text_fact(
                category="preference",
                key="self_reported_learning_style",
                value=getattr(about, "style", ""),
                confidence=1.0,
                importance=0.85,
            )
            sync_text_fact(
                category="interaction",
                key="self_reported_other",
                value=getattr(about, "other", ""),
                confidence=0.9,
                importance=0.6,
            )

        explicit_interests: list[str] | None = None
        if preferences is not None:
            explicit_interests = []
            for interest in getattr(preferences, "interests", []) or []:
                interest = str(interest).strip()
                if interest and interest not in explicit_interests:
                    explicit_interests.append(interest)

            desired_keys = {f"self_reported_interest:{x}" for x in explicit_interests}
            existing = fact_repo.list_active_by_source(
                user_id, "user_preferences", category="interest"
            )
            for row in existing:
                if row.get("key") not in desired_keys:
                    fact_repo.archive_fact(
                        user_id,
                        "interest",
                        row["key"],
                        source_ref="user_preferences",
                        reason="user_interest_removed",
                    )

            for interest in explicit_interests:
                fact_repo.upsert_candidate(
                    user_id,
                    category="interest",
                    key=f"self_reported_interest:{interest}",
                    value=interest,
                    evidence_type="explicit",
                    confidence=1.0,
                    importance=0.75,
                    source_ref="user_preferences",
                )

        overview_repo = ProfileOverviewRepository()
        overview = overview_repo.refresh_source_snapshot(user_id)
        if explicit_interests is not None:
            overview_repo.upsert(
                user_id,
                overall_judgement=(overview or {}).get("overall_judgement", ""),
                interests=explicit_interests,
                learning_level=(overview or {}).get("learning_level", ""),
                knowledge_scope=(overview or {}).get("knowledge_scope", ""),
                dialogue_preference=(overview or {}).get("dialogue_preference", ""),
                learning_behavior=(overview or {}).get("learning_behavior", ""),
                weakness_summary=(overview or {}).get("weakness_summary", ""),
                strategy_summary=(overview or {}).get("strategy_summary", ""),
                source_snapshot=(overview or {}).get("source_snapshot", {}),
                facts_snapshot=overview_repo.build_facts_snapshot(user_id),
            )
        logger.info("已同步用户自填信息到统一画像")

    # ------------------------------------------------------------------
    # Dashboard 聚合
    # ------------------------------------------------------------------

    async def get_dashboard(self, user_id: str) -> DashboardStats:
        """聚合 dashboard 所需的全部数据：节点统计 / 学习打卡 / 最近会话 / AI 学习计划。"""
        node_counts = self.node_repo.count(user_id)
        streak = self.study_log_repo.get_streak(user_id)
        study_logs_raw = self.study_log_repo.get_recent(user_id, 84)
        study_logs = [
            StudyLogSchema(date=r["date"], minutes=r["minutes"]) for r in study_logs_raw
        ]

        sessions = self.session_repo.get_all(user_id, limit=5)
        recent_sessions: list[Dict[str, Any]] = [
            {
                "id": s.id,
                "title": s.title,
                "topic": s.topic,
                "created_at": str(s.created_at),
                "duration_minutes": s.duration_minutes,
            }
            for s in sessions
        ]

        plan = await DailyPlanService().get_or_generate(user_id)

        return DashboardStats(
            total_nodes=node_counts["total"],
            mastered_nodes=node_counts["mastered"],
            due_today=node_counts["due_today"],
            streak_days=streak,
            study_logs=study_logs,
            recent_sessions=recent_sessions,
            tasks=plan.get("tasks", []),
            ai_recommendation=plan.get("recommendation", {}),
        )
