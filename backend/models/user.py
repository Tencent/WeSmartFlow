"""
User 模型
"""

from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import Field
from .base import BaseSchema


class UserPreferences(BaseSchema):
    daily_goal_minutes: int = 30
    reminder_enabled: bool = True
    difficulty_level: Literal["easy", "medium", "hard", "auto"] = "auto"
    interests: list[str] = []


class UserAbout(BaseSchema):
    background: str = ""  # 学习背景
    goals: str = ""  # 学习目标
    style: str = ""  # 学习偏好
    other: str = ""  # 其他补充


class UserSchema(BaseSchema):
    id: str
    name: str
    avatar_url: Optional[str]
    preferences: UserPreferences
    about: UserAbout = Field(default_factory=UserAbout)
    created_at: datetime


class UserUpdate(BaseSchema):
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    preferences: Optional[UserPreferences] = None
    about: Optional[UserAbout] = None


# ---------- Dashboard 统计 ----------


class StudyLogSchema(BaseSchema):
    date: str  # YYYY-MM-DD
    minutes: int


class DashboardStats(BaseSchema):
    total_nodes: int
    mastered_nodes: int  # mastery_level >= 0.8
    due_today: int  # due_date <= today
    streak_days: int  # 连续学习天数
    study_logs: list[StudyLogSchema]  # 最近 84 天（热力图用，12周）
    recent_sessions: list[dict]  # 最近5次会话摘要
    tasks: list[dict] = []  # AI 生成的今日任务
    ai_recommendation: dict = {}  # AI 个性化推荐
