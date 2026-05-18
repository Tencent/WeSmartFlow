"""用户与 Dashboard 路由：获取/更新用户信息、Dashboard 聚合统计。"""

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user
from models.user import DashboardStats, UserUpdate
from services import UserService

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("")
def get_user(user_id: str = Depends(get_current_user)):
    user = UserService().get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


@router.patch("")
def update_user(data: UserUpdate, user_id: str = Depends(get_current_user)):
    return UserService().update_user(
        user_id,
        name=data.name,
        avatar_url=data.avatar_url,
        preferences=data.preferences,
        about=data.about,
    )


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(user_id: str = Depends(get_current_user)):
    return await UserService().get_dashboard(user_id)
