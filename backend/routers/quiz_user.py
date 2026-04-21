"""
测验路由 & 用户/Dashboard 路由
"""

import sqlite3
from fastapi import APIRouter, Depends, HTTPException

from database import get_db_dep
from models.quiz import QuizSubmit
from models.user import UserUpdate, DashboardStats, StudyLogSchema
from repositories import NodeRepository, UserRepository
from repositories.quiz_repo import StudyLogRepository
from services import QuizService

# ---------- Quiz ----------
quiz_router = APIRouter(prefix="/api/quiz", tags=["quiz"])
USER_ID = "default"


@quiz_router.post("/generate/{node_id}")
async def generate_quiz(
    node_id: str,
    quiz_type: str = "multiple_choice",
    session_id: str = None,
    db: sqlite3.Connection = Depends(get_db_dep),
):
    try:
        return await QuizService(db).generate_quiz(
            USER_ID, node_id, session_id, quiz_type
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@quiz_router.post("/{quiz_id}/submit")
async def submit_quiz(
    quiz_id: str, body: QuizSubmit, db: sqlite3.Connection = Depends(get_db_dep)
):
    try:
        return await QuizService(db).submit_answer(quiz_id, body.answer)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ---------- User & Dashboard ----------
user_router = APIRouter(prefix="/api/user", tags=["user"])


@user_router.get("")
def get_user(db: sqlite3.Connection = Depends(get_db_dep)):
    return UserRepository(db).get_or_create_default()


@user_router.patch("")
def update_user(data: UserUpdate, db: sqlite3.Connection = Depends(get_db_dep)):
    return UserRepository(db).update(
        USER_ID,
        name=data.name,
        avatar_url=data.avatar_url,
        preferences=data.preferences,
        about=data.about,
    )


@user_router.get("/dashboard", response_model=DashboardStats)
async def dashboard(db: sqlite3.Connection = Depends(get_db_dep)):
    node_counts = NodeRepository(db).count(USER_ID)
    streak = StudyLogRepository(db).get_streak(USER_ID)
    study_logs_raw = StudyLogRepository(db).get_recent(USER_ID, 84)
    study_logs = [
        StudyLogSchema(date=r["date"], minutes=r["minutes"]) for r in study_logs_raw
    ]

    # 最近5次会话
    from repositories import SessionRepository

    sessions = SessionRepository(db).get_all(USER_ID, limit=5)
    recent_sessions = [
        {
            "id": s.id,
            "title": s.title,
            "topic": s.topic,
            "created_at": str(s.created_at),
            "duration_minutes": s.duration_minutes,
        }
        for s in sessions
    ]

    # AI 生成的今日学习计划（有缓存直接返回，无缓存异步生成）
    from services import DailyPlanService

    plan = await DailyPlanService(db).get_or_generate(USER_ID)

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


# ---------- Daily Brief ----------
brief_router = APIRouter(prefix="/api/brief", tags=["brief"])


@brief_router.get("")
async def get_brief(db: sqlite3.Connection = Depends(get_db_dep)):
    """获取今日资讯简报（有缓存直接返回，否则生成）"""
    from services import DailyBriefService

    return await DailyBriefService(db).get_or_generate(USER_ID)


@brief_router.post("/regenerate")
async def regenerate_brief(db: sqlite3.Connection = Depends(get_db_dep)):
    """强制重新生成今日简报"""
    from services import DailyBriefService

    return await DailyBriefService(db).regenerate(USER_ID)


@brief_router.get("/dates")
def get_brief_dates(db: sqlite3.Connection = Depends(get_db_dep)):
    """获取所有有简报数据的日期列表"""
    from services import DailyBriefService

    dates = DailyBriefService(db).get_dates_with_data(USER_ID)
    return {"dates": dates}


@brief_router.get("/{date}")
async def get_brief_by_date(date: str, db: sqlite3.Connection = Depends(get_db_dep)):
    """获取指定日期的简报（仅读缓存）"""
    from services import DailyBriefService

    return await DailyBriefService(db).get_by_date(USER_ID, date)
