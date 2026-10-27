"""单文档、短时效的文件访问票据。

iframe / web-view / 微信链接无法携带 ``Authorization`` 头，过去的做法是把
**完整的用户登录 JWT** 放进 URL（``?token=``）并写入 Cookie。URL 会进入访问日志、
浏览器历史、Referer 与聊天记录，泄露后等价于 72 小时的完整账号接管。

票据只解决“读取某一个文档”这一件事：

- 独立 audience 与派生密钥，不能当登录 token 使用，登录 token 也不能当票据；
- 绑定具体 ``doc`` id，换一个文档即失效；
- 有效期短，由调用方按场景指定。
"""

from __future__ import annotations

import jwt

from config import JWT_SECRET
from utils.jwt_tokens import FILE_TICKET_AUDIENCE, decode_token, encode_token

DEFAULT_TICKET_MINUTES = 30
MAX_TICKET_MINUTES = 24 * 60


def create_file_ticket(
    user_id: str, doc_id: str, *, expires_in_minutes: int = DEFAULT_TICKET_MINUTES
) -> str:
    minutes = max(1, min(int(expires_in_minutes), MAX_TICKET_MINUTES))
    return encode_token(
        subject=user_id,
        audience=FILE_TICKET_AUDIENCE,
        master_secret=JWT_SECRET,
        expires_in_hours=minutes / 60,
        extra_claims={"doc": str(doc_id)},
    )


def verify_file_ticket(ticket: str, doc_id: str) -> str:
    """校验票据并返回 user_id；失败抛出 ``jwt.InvalidTokenError``。"""
    payload = decode_token(
        ticket, audience=FILE_TICKET_AUDIENCE, master_secret=JWT_SECRET
    )
    if payload.get("doc") != str(doc_id):
        raise jwt.InvalidTokenError("票据不属于该文档")
    return payload["sub"]
