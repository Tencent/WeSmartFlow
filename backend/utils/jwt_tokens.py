"""JWT 签发与校验的统一实现。

安全约束：

- 算法固定为 HS256，且不读取环境变量，避免 alg 混淆/降级；
- 用户 token 与管理员 token 使用由主密钥派生的两把独立签名密钥，
  并分别绑定独立 audience：即使某一侧校验被误删，另一侧 token 也
  无法越权使用；
- 强制校验 iss/aud/sub/iat/exp，拒绝缺省 claim 或异常 subject；
- 每次签发带随机 jti，便于后续审计与吊销能力扩展。
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "wesmartflow"
USER_TOKEN_AUDIENCE = "wesmartflow:user"
ADMIN_TOKEN_AUDIENCE = "wesmartflow:admin"
FILE_TICKET_AUDIENCE = "wesmartflow:file"

# 令牌长度上限：防止超长 token 占用签名校验资源。
MAX_TOKEN_LENGTH = 4096
# 允许的时钟偏差：只用于判断 iat 是否“来自未来”。
MAX_CLOCK_SKEW_SECONDS = 60

_REQUIRED_CLAIMS = ["sub", "iat", "exp", "iss", "aud"]
_SUBJECT_PATTERN = re.compile(r"^[A-Za-z0-9_.:@-]{1,128}$")


def derive_signing_key(master_secret: str, audience: str) -> bytes:
    """从主密钥派生指定用途的签名密钥（HMAC-SHA256 域分离）。"""
    if not master_secret:
        raise ValueError("JWT 主密钥不能为空")
    return hmac.new(
        master_secret.encode("utf-8"),
        f"wesmartflow/jwt/v1/{audience}".encode("utf-8"),
        hashlib.sha256,
    ).digest()


def encode_token(
    *,
    subject: str,
    audience: str,
    master_secret: str,
    expires_in_hours: float,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """签发带 iss/aud/iat/exp/jti 的 token。"""
    if not isinstance(subject, str) or not _SUBJECT_PATTERN.fullmatch(subject):
        raise ValueError("非法的 token subject")
    if expires_in_hours <= 0:
        raise ValueError("token 有效期必须大于 0")

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iss": JWT_ISSUER,
        "aud": audience,
        "iat": now,
        "exp": now + timedelta(hours=expires_in_hours),
        "jti": secrets.token_hex(16),
    }
    for key, value in (extra_claims or {}).items():
        if key in payload:
            raise ValueError(f"不能覆写保留 claim: {key}")
        payload[key] = value

    return jwt.encode(
        payload,
        derive_signing_key(master_secret, audience),
        algorithm=JWT_ALGORITHM,
    )


def decode_token(token: str, *, audience: str, master_secret: str) -> dict[str, Any]:
    """校验并返回 payload；任何不合法情况都抛出 ``jwt.InvalidTokenError``。"""
    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
        raise jwt.InvalidTokenError("token 缺失或长度异常")

    payload = jwt.decode(
        token,
        derive_signing_key(master_secret, audience),
        algorithms=[JWT_ALGORITHM],
        audience=audience,
        issuer=JWT_ISSUER,
        options={"require": _REQUIRED_CLAIMS},
    )

    subject = payload.get("sub")
    if not isinstance(subject, str) or not _SUBJECT_PATTERN.fullmatch(subject):
        raise jwt.InvalidTokenError("非法的 token subject")

    issued_at = payload.get("iat")
    now = int(datetime.now(timezone.utc).timestamp())
    if isinstance(issued_at, int) and issued_at > now + MAX_CLOCK_SKEW_SECONDS:
        raise jwt.InvalidTokenError("token 签发时间在未来")

    return payload
