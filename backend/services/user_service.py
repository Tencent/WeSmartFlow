"""
UserService：用户与 Dashboard 的业务逻辑层。

把原本散落在 ``routers/quiz_user.py`` 里 dashboard 端点的拼装逻辑下沉到此处，
让 router 层回归"参数校验 + 调用 service"的薄壳。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from models.user import DashboardStats, StudyLogSchema
from repositories import NodeRepository, SessionRepository, UserRepository
from repositories.quiz_repo import StudyLogRepository
from services.daily_plan_service import DailyPlanService


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
        return self.user_repo.update(
            user_id,
            name=name,
            avatar_url=avatar_url,
            preferences=preferences,
            about=about,
        )

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
