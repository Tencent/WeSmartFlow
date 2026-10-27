"""Web 鉴权工具：为受保护的文件资源兼容多种凭据来源。

主流程仍走 ``Authorization: Bearer <登录 token>``。iframe / web-view / 微信链接
无法注入 header，这些场景只接受 **绑定单个文档的短时效票据**
（见 ``utils/file_ticket.py``），来源可以是 ``?ticket=`` 或同文档路径下的 Cookie。
完整的登录 token 不再允许出现在 URL 或 Cookie 里。

返回 ``(user_id, query_ticket_or_none)``：当来源是 query 时，调用方应把票据写入
限定在该文档路径下的 ``Set-Cookie``，让后续子资源请求自动鉴权。
"""

from __future__ import annotations

import jwt
from fastapi import HTTPException, Request

from dependencies import decode_access_token
from utils.file_ticket import verify_file_ticket

# 同域 cookie 名（与前端无关，前端只用 localStorage）
COOKIE_NAME = "wesmartflow_file_ticket"


def get_user_from_request_flexible(
    request: Request, doc_id: str
) -> tuple[str, str | None]:
    """解析访问 ``doc_id`` 的用户。

    优先级：``Authorization`` > ``?ticket=`` > Cookie。全部失败抛 401。
    """
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        bearer = auth.split(" ", 1)[1].strip()
        if bearer:
            return decode_access_token(bearer), None

    query_ticket = request.query_params.get("ticket")
    ticket = query_ticket or request.cookies.get(COOKIE_NAME)
    if not ticket:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        return verify_file_ticket(ticket, doc_id), query_ticket
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="访问链接已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的访问链接")
