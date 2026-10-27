"""JWT 鉴权依赖

提供 token 创建、验证和 FastAPI 依赖注入。

用户 token 与管理员 token 使用不同的派生签名密钥和 audience，
``decode_access_token`` 只接受用户 token，管理员 token 无法冒充普通用户，
反之亦然。
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import JWT_EXPIRE_HOURS, JWT_SECRET
from utils.jwt_tokens import USER_TOKEN_AUDIENCE, decode_token, encode_token

# Missing credentials are authentication failures.  Returning 401 keeps the
# browser and mini-program clients on the same re-login path as expired JWTs.
security = HTTPBearer(auto_error=False)


def create_access_token(user_id: str) -> str:
    """生成用户 JWT access token。"""
    return encode_token(
        subject=user_id,
        audience=USER_TOKEN_AUDIENCE,
        master_secret=JWT_SECRET,
        expires_in_hours=JWT_EXPIRE_HOURS,
    )


def decode_access_token(token: str) -> str:
    """解析用户 JWT token，返回 user_id；验证失败抛出 401。"""
    try:
        payload = decode_token(
            token, audience=USER_TOKEN_AUDIENCE, master_secret=JWT_SECRET
        )
        user_id = payload.get("sub")
        if not isinstance(user_id, str) or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证凭据",
            )
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已过期",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Token",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """
    FastAPI 依赖：从 Authorization: Bearer <token> 中解析出 user_id。
    验证失败抛出 401。
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)
