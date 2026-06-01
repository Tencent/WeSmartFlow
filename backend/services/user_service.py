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
from config import DOCUMENTS_DIR

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
        # 同步 about 到 profile.md，让 Agent 能读取用户画像
        if about is not None:
            try:
                self._sync_about_to_profile(user_id, about)
            except Exception as e:
                logger.warning("同步 about 到 profile.md 失败: %s", e)
        return result

    def _sync_about_to_profile(self, user_id: str, about) -> None:
        """将用户自填的 about 信息同步写入 profile.md 的「自我描述」部分。

        保留 profile.md 中 AI 观察到的其他部分（如学习特征、知识点掌握度），
        只更新「自我描述」段落。
        """
        from agent_core.layout import UserDataLayout

        layout = UserDataLayout(root=DOCUMENTS_DIR, user_id=user_id)
        layout.ensure_dirs()
        profile_file = layout.profile_file

        # 构建「自我描述」段落
        sections = []
        if hasattr(about, "background") and about.background:
            sections.append(f"- 学习背景：{about.background}")
        if hasattr(about, "goals") and about.goals:
            sections.append(f"- 学习目标：{about.goals}")
        if hasattr(about, "style") and about.style:
            sections.append(f"- 学习偏好：{about.style}")
        if hasattr(about, "other") and about.other:
            sections.append(f"- 其他：{about.other}")

        if not sections:
            return  # 没有有效内容，不写入

        new_self_desc = "## 自我描述\n\n" + "\n".join(sections)

        # 读取现有 profile.md，保留非「自我描述」部分
        existing_content = ""
        if profile_file.exists():
            existing_content = profile_file.read_text(encoding="utf-8")

        if existing_content:
            # 替换已有的「自我描述」段落
            import re

            pattern = r"## 自我描述\n[\s\S]*?(?=\n## |\Z)"
            if re.search(pattern, existing_content):
                updated = re.sub(pattern, new_self_desc, existing_content, count=1)
            else:
                # 没有「自我描述」段落，插入到开头
                updated = new_self_desc + "\n\n" + existing_content
        else:
            # 全新文件
            updated = "# 用户画像\n\n" + new_self_desc + "\n"

        profile_file.write_text(updated, encoding="utf-8")
        logger.info("已同步用户 about 到 profile.md")

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
