"""
Quiz（测验）模型
"""

from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import Field
from .base import BaseSchema


class QuizSchema(BaseSchema):
    id: str
    user_id: str
    node_id: str
    session_id: Optional[str]
    quiz_type: Literal["multiple_choice", "fill_in", "true_false", "open_ended"]
    question: str
    options: Optional[list[str]]
    correct_answer: str
    explanation: str
    # 作答状态
    user_answer: Optional[str]
    is_correct: Optional[bool]
    score: Optional[float]
    answered_at: Optional[datetime]
    created_at: datetime


class QuizSubmit(BaseSchema):
    """用户提交答案"""

    answer: str


class QuizResult(BaseSchema):
    quiz_id: str
    is_correct: bool
    score: float
    correct_answer: str
    explanation: str
    mastery_delta: float = Field(description="该节点掌握度变化量")
