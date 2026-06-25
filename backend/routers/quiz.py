"""测验（Quiz）路由：生成测验、提交答案。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user
from models.quiz import QuizSubmit
from services import QuizService
from utils.validators import is_valid_session_id

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


@router.post("/generate/{node_id}")
async def generate_quiz(
    node_id: str,
    quiz_type: str = "multiple_choice",
    session_id: Optional[str] = None,
    user_id: str = Depends(get_current_user),
):
    if session_id is not None and not is_valid_session_id(session_id):
        raise HTTPException(status_code=400, detail="非法 session_id")
    try:
        return await QuizService().generate_quiz(
            user_id, node_id, session_id, quiz_type
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{quiz_id}")
async def get_quiz(
    quiz_id: str,
    user_id: str = Depends(get_current_user),
):
    try:
        return QuizService().get_quiz(user_id, quiz_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{quiz_id}/submit")
async def submit_quiz(
    quiz_id: str,
    body: QuizSubmit,
    user_id: str = Depends(get_current_user),
):
    try:
        return await QuizService().submit_answer(user_id, quiz_id, body.answer)
    except ValueError as e:
        raise HTTPException(404, str(e))
