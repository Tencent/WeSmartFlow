"""
API 使用量路由
GET  /api/usage  → 返回当前用户各类别的累计使用量和总额度
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from dependencies import get_current_user
from services.quota import get_usage

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
def usage_summary(user_id: str = Depends(get_current_user)):
    """返回当前用户各类别的累计使用量和总额度信息。"""
    return get_usage(user_id)
