"""
轻量级 LLM 问答接口（不走 Agent，纯 LLM 一问一答）

用于"问AI"功能：用户选中文本后快速获取解释，无需工具调用。
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent_core.llm.base import StreamChunkEvent, StreamFinishEvent
from dependencies import get_current_user
from services.llm_factory import get_llm
from services.content_guard import get_content_guard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm", tags=["llm"])


class QuickAskRequest(BaseModel):
    """轻量级问答请求体"""

    question: str  # 用户选中的文本或问题
    context: str = ""  # 可选的上下文（如当前学习主题）


@router.post("/quick-ask")
async def quick_ask(
    request: Request,
    body: QuickAskRequest,
    user_id: str = Depends(get_current_user),
):
    """
    轻量级 LLM 流式问答接口。

    不走 Agent 通道，直接调用 LLM 流式返回文本。
    SSE 事件格式：
    - text_chunk: { type: "text_chunk", delta: "..." }
    - done: { type: "done" }
    - error: { type: "error", message: "..." }
    """
    # ── 内容安全审核（输入） ──
    guard = get_content_guard()
    if guard.enabled:
        guard_result = await guard.check_input(body.question)
        if not guard_result.is_safe:
            guard.log_violation(user_id, body.question, guard_result)
            err_data = json.dumps(
                {
                    "type": "error",
                    "message": guard_result.reason,
                    "code": "content_blocked",
                },
                ensure_ascii=False,
            )

            async def blocked_stream():
                yield f"data: {err_data}\n\n"

            return StreamingResponse(
                blocked_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

    llm = get_llm(user_id)

    # 构造简单的消息列表
    messages = []

    # system prompt
    system_content = "你是一个知识渊博的学习助手。请用简洁易懂的语言解释用户选中的内容，可以举例说明。回答要精炼，避免冗长。支持使用 LaTeX 数学公式（用 $ 或 $$ 包裹）。"
    if body.context:
        system_content += f"\n\n当前学习上下文：{body.context}"

    messages.append({"role": "system", "content": system_content})
    messages.append({"role": "user", "content": body.question})

    async def event_stream():
        try:
            async for event in llm.stream_think(messages, tools=None, tool_choice=None):
                # 检查客户端是否断开
                if await request.is_disconnected():
                    break

                if isinstance(event, StreamChunkEvent):
                    data = json.dumps(
                        {"type": "text_chunk", "delta": event.delta},
                        ensure_ascii=False,
                    )
                    yield f"data: {data}\n\n"
                elif isinstance(event, StreamFinishEvent):
                    # 流结束
                    done_data = json.dumps({"type": "done"}, ensure_ascii=False)
                    yield f"data: {done_data}\n\n"
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("quick-ask 出错: %s", e)
            err = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
