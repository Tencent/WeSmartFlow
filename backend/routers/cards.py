"""
卡片静态文件路由（带鉴权）

替代原先的 `app.mount("/files/cards", StaticFiles(...))`，
因为 StaticFiles 无法注入 FastAPI Depends，无法做鉴权。

资源命名约定（与 agents/tools/generate_card.py 对齐）：
  - PDF:        {card_id}/card.pdf
  - 音频目录:   {card_id}/audio/frame_{num}.wav
  - 讲解稿:     {card_id}/notes.json
  - LaTeX源:    {card_id}/card.tex

权属校验：取 file_path 第一段（按 '/' 切），
得到 card_id（即 documents.id），然后查 documents.user_id 是否匹配当前用户。
"""

from __future__ import annotations

import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from config import CARDS_DIR
from database import get_db
from dependencies import decode_access_token, get_current_user
from services.quota import QuotaExceededError

logger = logging.getLogger(__name__)

# 静态文件路由
router = APIRouter(prefix="/files/cards", tags=["cards"])

# ---------- HTML 卡片生成（SSE 流式） ----------
gen_router = APIRouter(prefix="/api/cards", tags=["cards-gen"])


class GenerateHtmlCardRequest(BaseModel):
    title: str
    content: str
    node_ids: list[str] = []


@gen_router.post("/generate-html")
async def generate_html_card(
    req: GenerateHtmlCardRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    """
    SSE 流式生成 HTML 交互卡片。

    事件格式：data: <JSON>：
      { type: "progress", message: "..." }   — 进度信息
      { type: "result",   file_id: "...", script: "..." }  — 生成结果
      { type: "error",    message: "..." }   — 错误
      { type: "done" }                        — 完成
    """
    from agents.tools.generate_html_card import GenerateHtmlCardTool

    async def event_stream():
        tool = GenerateHtmlCardTool(user_id=user_id, session_id=None)
        try:
            async for event in tool.async_stream_run(
                title=req.title,
                content=req.content,
                node_ids=req.node_ids,
            ):
                if await request.is_disconnected():
                    break

                # 最终 JSON 结果字符串
                if isinstance(event, str):
                    text = event
                    # 尝试解析为结果 JSON
                    try:
                        parsed = json.loads(text)
                        if "file_id" in parsed:
                            yield f"data: {json.dumps({'type': 'result', **parsed}, ensure_ascii=False)}\n\n"
                            continue
                    except (json.JSONDecodeError, TypeError):
                        pass
                    # 普通进度文字
                    yield f"data: {json.dumps({'type': 'progress', 'message': text}, ensure_ascii=False)}\n\n"
                # AgentFinalEvent 不需要透传给前端
        except asyncio.CancelledError:
            pass
        except QuotaExceededError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e), 'code': 'quota_exceeded'}, ensure_ascii=False)}\n\n"
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("[generate_html_card] 生成失败")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _extract_card_id(file_path: str) -> str | None:
    """
    从 file_path 推导 card_id（即 documents.id，通常是 uuid）。

    支持：
      "{card_id}/card.pdf"              → "{card_id}"
      "{card_id}/card.tex"              → "{card_id}"
      "{card_id}/audio/frame_001.wav"   → "{card_id}"
      "{card_id}/notes.json"            → "{card_id}"
    """
    first = file_path.replace("\\", "/").strip("/").split("/", 1)[0]
    return first or None


def _assert_card_owner(user_id: str, file_path: str) -> None:
    """校验 file_path 对应的 card 是否属于当前用户；不属于/不存在统一 404。"""
    card_id = _extract_card_id(file_path)
    if not card_id:
        raise HTTPException(status_code=404, detail="文件不存在")

    with get_db() as conn:
        cur = conn.execute(
            "SELECT user_id FROM documents WHERE id = ? LIMIT 1", (card_id,)
        )
        row = cur.fetchone()

    if row is None or row["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="文件不存在")


def _get_card_request_user(request: Request) -> tuple[str, str | None]:
    """
    卡片文件鉴权：
    - 小程序 wx.downloadFile / getText 使用 Authorization header；
    - web-view 无法注入 header，所以支持 ?token=xxx；
    - card.html 内部图片等子资源不带 query 时，使用首次 HTML 响应写入的 cookie。
    返回 (user_id, query_token)。
    """
    auth = request.headers.get("authorization") or ""
    token = None
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    query_token = request.query_params.get("token")
    if not token:
        token = query_token or request.cookies.get("ascendflow_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_access_token(token), query_token


@router.api_route("/{file_path:path}", methods=["GET", "HEAD"])
async def serve_card_file(
    file_path: str,
    request: Request,
):
    """提供生成的卡片静态文件（PDF/音频/讲解稿等），需鉴权 + 归属校验。"""
    user_id, query_token = _get_card_request_user(request)
    full_path = (CARDS_DIR / file_path).resolve()

    # 防止路径穿越
    if not str(full_path).startswith(str(CARDS_DIR.resolve())):
        raise HTTPException(status_code=403, detail="路径不允许")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    _assert_card_owner(user_id, file_path)

    suffix = full_path.suffix.lower()
    media_types = {
        ".pdf": "application/pdf",
        ".html": "text/html; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".json": "application/json; charset=utf-8",
        ".tex": "text/plain; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
    }
    headers = {}
    if query_token:
        # web-view 首次以 ?token=xxx 打开 card.html 后，后续图片/脚本等子资源请求
        # 无法携带 Authorization header，也不会自动带 query；写入同域 cookie 兜底鉴权。
        headers["Set-Cookie"] = (
            f"ascendflow_token={query_token}; Path=/; HttpOnly; SameSite=Lax"
        )
    return FileResponse(
        path=full_path,
        media_type=media_types.get(suffix, "application/octet-stream"),
        headers=headers,
    )
