"""
Admin 审核台鉴权工具

独立于普通用户体系：
- 账号密码从 .env 读取（ADMIN_USERNAME / ADMIN_PASSWORD），常量时间比对
- token 使用由主密钥派生的 admin 专用签名密钥，携带独立 audience，
  sub="admin"、claim role="admin"、有效期更短
- token 额外绑定当前管理员口令的指纹：修改口令后旧 token 立即失效
- 未配置管理员账号时，所有 admin 接口直接 503，而不是只拦登录接口
"""

from __future__ import annotations

import hashlib
import hmac
import logging

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import (
    ADMIN_PASSWORD,
    ADMIN_TOKEN_EXPIRE_HOURS,
    ADMIN_USERNAME,
    JWT_SECRET,
)
from utils.jwt_tokens import (
    ADMIN_TOKEN_AUDIENCE,
    decode_token,
    derive_signing_key,
    encode_token,
)

logger = logging.getLogger(__name__)

_admin_security = HTTPBearer(auto_error=True)

ADMIN_SUB = "admin"
ADMIN_ROLE = "admin"
_CREDENTIAL_CLAIM = "cred"

ADMIN_NOT_CONFIGURED_DETAIL = (
    "Admin 未配置（请在 .env 中设置 ADMIN_USERNAME / ADMIN_PASSWORD）"
)


def admin_credentials_configured() -> bool:
    return bool(ADMIN_USERNAME.strip()) and bool(ADMIN_PASSWORD)


def _constant_time_equals(value: str, expected: str) -> bool:
    return hmac.compare_digest(
        (value or "").encode("utf-8"), (expected or "").encode("utf-8")
    )


def verify_admin_credentials(username: str, password: str) -> bool:
    """常量时间比对。.env 未配置则永远返回 False。"""
    if not admin_credentials_configured():
        return False
    username_ok = _constant_time_equals(username, ADMIN_USERNAME)
    password_ok = _constant_time_equals(password, ADMIN_PASSWORD)
    return username_ok and password_ok


def _credential_fingerprint() -> str:
    """当前管理员口令的 HMAC 指纹，用于让旧 token 随口令轮换失效。"""
    material = (
        f"{len(ADMIN_USERNAME)}:{ADMIN_USERNAME}{len(ADMIN_PASSWORD)}:{ADMIN_PASSWORD}"
    )
    return hmac.new(
        derive_signing_key(JWT_SECRET, ADMIN_TOKEN_AUDIENCE),
        material.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_admin_token() -> str:
    """生成 admin JWT；未配置管理员账号时拒绝签发。"""
    if not admin_credentials_configured():
        raise RuntimeError(ADMIN_NOT_CONFIGURED_DETAIL)

    return encode_token(
        subject=ADMIN_SUB,
        audience=ADMIN_TOKEN_AUDIENCE,
        master_secret=JWT_SECRET,
        expires_in_hours=ADMIN_TOKEN_EXPIRE_HOURS,
        extra_claims={
            "role": ADMIN_ROLE,
            _CREDENTIAL_CLAIM: _credential_fingerprint(),
        },
    )


def _decode_admin_token(token: str) -> dict:
    try:
        payload = decode_token(
            token, audience=ADMIN_TOKEN_AUDIENCE, master_secret=JWT_SECRET
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin token 已过期",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Admin token",
        ) from exc

    if payload.get("sub") != ADMIN_SUB or payload.get("role") != ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="非 admin 凭据",
        )

    presented = payload.get(_CREDENTIAL_CLAIM)
    if not isinstance(presented, str) or not hmac.compare_digest(
        presented, _credential_fingerprint()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin 凭据已失效，请重新登录",
        )

    return payload


def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_admin_security),
) -> str:
    """FastAPI 依赖：要求请求带合法的 admin token，返回固定字符串 'admin'。

    未配置管理员账号时一律 503：即使有人用旧密钥/伪造 claim 造出
    sub=admin、role=admin 的 token，也不会获得任何管理能力。
    """
    if not admin_credentials_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ADMIN_NOT_CONFIGURED_DETAIL,
        )

    _decode_admin_token(credentials.credentials)
    return ADMIN_SUB
