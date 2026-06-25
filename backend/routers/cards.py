"""HTML 卡片生成（SSE 流式）路由。

卡片文件读取统一走 ``/api/documents/{doc_id}/raw``（``card.html`` 主资源）+
``/api/documents/{doc_id}/asset/images/xxx.png``（伴生图片），本路由只负责生成入口。
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from dependencies import get_current_user
from services.quota import QuotaExceededError

logger = logging.getLogger(__name__)


# ── HTML 卡片生成（SSE 流式） ─────────────────────────────────────

gen_router = APIRouter(prefix="/api/cards", tags=["cards"])


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
    """SSE 流式生成 HTML 交互卡片。

    事件格式：``data: <JSON>``：
      - ``{ type: "progress", message: "..." }`` — 进度信息
      - ``{ type: "result",   file_id: "...", script: "..." }`` — 生成结果
      - ``{ type: "error",    message: "..." }`` — 错误
      - ``{ type: "done" }`` — 完成
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

                if isinstance(event, str):
                    text = event
                    try:
                        parsed = json.loads(text)
                        if "file_id" in parsed:
                            yield f"data: {json.dumps({'type': 'result', **parsed}, ensure_ascii=False)}\n\n"
                            continue
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.exception(
                            "[generate_html_card] JSON 解析失败, error: %s, text: %s",
                            e,
                            text,
                        )

                    yield f"data: {json.dumps({'type': 'progress', 'message': text}, ensure_ascii=False)}\n\n"
                # AgentFinalEvent / 其它流式事件忽略
        except asyncio.CancelledError:
            logger.info("[generate_html_card] 生成被取消")
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
