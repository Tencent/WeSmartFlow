"""每日资讯简报（Daily Brief）路由。"""

from fastapi import APIRouter, Depends

from dependencies import get_current_user
from services import DailyBriefService

router = APIRouter(prefix="/api/brief", tags=["brief"])


@router.get("")
async def get_brief(user_id: str = Depends(get_current_user)):
    """获取今日资讯简报（有缓存直接返回，否则生成）。"""
    return await DailyBriefService().get_or_generate(user_id)


@router.post("/regenerate")
async def regenerate_brief(user_id: str = Depends(get_current_user)):
    """强制重新生成今日简报。"""
    return await DailyBriefService().regenerate(user_id)


@router.get("/dates")
def get_brief_dates(user_id: str = Depends(get_current_user)):
    """获取所有有简报数据的日期列表。"""
    dates = DailyBriefService().get_dates_with_data(user_id)
    return {"dates": dates}


@router.get("/{date}")
async def get_brief_by_date(date: str, user_id: str = Depends(get_current_user)):
    """获取指定日期的简报（仅读缓存）。"""
    return await DailyBriefService().get_by_date(user_id, date)
