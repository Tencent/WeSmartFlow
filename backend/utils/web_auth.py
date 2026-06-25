"""Web 鉴权工具：兼容多种 token 来源。

主流程仍走 ``Authorization: Bearer <token>``；但下列两种场景需要降级：

1. 浏览器 ``<iframe>`` 加载受保护资源时无法注入自定义 header，
   首次以 ``?token=xxx`` query 方式打开页面，后续同域子资源再走 cookie；
2. 小程序 web-view（暂不计划支持，但接口预留）。

返回 ``(user_id, query_token_or_none)``：当来源是 query 时，
调用方应把 ``query_token`` 写入 ``Set-Cookie``，让后续请求可自动鉴权。
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from dependencies import decode_access_token

# 同域 cookie 名（与前端无关，前端只用 localStorage）
COOKIE_NAME = "ascendflow_token"


def get_user_from_request_flexible(request: Request) -> tuple[str, str | None]:
    """从 request 上抽取 token 并解析出 user_id。

    优先级：``Authorization`` > ``?token=`` > Cookie。
    全部失败抛 401。
    """
    auth = request.headers.get("authorization") or ""
    token: str | None = None
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()

    query_token = request.query_params.get("token")
    if not token:
        token = query_token or request.cookies.get(COOKIE_NAME)

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return decode_access_token(token), query_token
