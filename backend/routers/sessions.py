"""
会话路由（含 SSE 流式聊天）
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from models.session import SessionCreate, ChatMessage, SessionSchema, SessionDetail
from services import TutorService
from agent_core.agent.base import (
    AgentThinkEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    AgentFinalEvent,
    FileCreatedEvent,
    NodeCreatedEvent,
    MasteryUpdatedEvent,
)
from dependencies import get_current_user
from services.quota import QuotaExceededError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSchema])
def list_sessions(user_id: str = Depends(get_current_user)):
    return TutorService().list_sessions(user_id)


@router.post("", response_model=SessionSchema, status_code=201)
def create_session(data: SessionCreate, user_id: str = Depends(get_current_user)):
    return TutorService().create_session(user_id, data)


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, user_id: str = Depends(get_current_user)):
    detail = TutorService().get_session_detail(user_id, session_id)
    if not detail:
        raise HTTPException(404, "会话不存在")
    return detail


@router.post("/{session_id}/chat/stream")
async def chat_stream(
    request: Request,
    session_id: str,
    body: ChatMessage,
    user_id: str = Depends(get_current_user),
):
    """
    SSE 流式聊天接口。

    每条 SSE 消息格式：data: <JSON>\\n\\n
    JSON 通过 type 字段区分事件类型：

    - thinking      — LLM 推理步骤  { type, content, step }
    - tool_call     — 工具调用      { type, tool, args, step }
    - tool_result   — 工具结果      { type, tool, result, step }
    - text_reply    — 最终回复文本  { type, text }   （一次性完整文本）
    - done          — 回复完成      { type, mastery_changes }
    - file_created  — 文件生成      { type, file_id }
    - node_created  — 节点创建      { type, node_id, title }
    - mastery_updated — 掌握度更新  { type, node_id, delta }
    - error         — 错误          { type, message }
    """
    service = TutorService()

    async def event_stream():
        """直接迭代 Agent 事件流，序列化为 SSE 格式输出。"""
        mastery_changes: dict[str, float] = {}
        try:
            async for event in service.stream_chat(user_id, session_id, body.content):
                # 检查客户端是否断开
                if await request.is_disconnected():
                    logger.info("客户端断开，停止生成")
                    break

                if isinstance(event, MasteryUpdatedEvent):
                    mastery_changes[event.node_id] = (
                        mastery_changes.get(event.node_id, 0.0) + event.delta
                    )
                    data = {
                        "type": "mastery_updated",
                        "node_id": event.node_id,
                        "delta": event.delta,
                    }
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                elif isinstance(event, AgentFinalEvent):
                    text_data = json.dumps(
                        {"type": "text_reply", "text": event.content},
                        ensure_ascii=False,
                    )
                    yield f"data: {text_data}\n\n"
                    done_data = json.dumps(
                        {"type": "done", "mastery_changes": mastery_changes},
                        ensure_ascii=False,
                    )
                    yield f"data: {done_data}\n\n"
                elif isinstance(event, AgentThinkEvent):
                    data = {
                        "type": "thinking",
                        "content": event.content,
                        "step": event.step,
                    }
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                elif isinstance(event, AgentToolCallEvent):
                    data = {
                        "type": "tool_call",
                        "tool": event.tool_name,
                        "args": event.arguments,
                        "step": event.step,
                    }
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                elif isinstance(event, AgentToolResultEvent):
                    data = {
                        "type": "tool_result",
                        "tool": event.tool_name,
                        "result": event.result,
                        "step": event.step,
                    }
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                elif isinstance(event, FileCreatedEvent):
                    data = {"type": "file_created", "file_id": event.file_id}
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                elif isinstance(event, NodeCreatedEvent):
                    data = {
                        "type": "node_created",
                        "node_id": event.node_id,
                        "title": event.title,
                    }
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            pass  # 客户端断开，静默退出
        except QuotaExceededError as e:
            err = json.dumps(
                {
                    "type": "error",
                    "message": str(e),
                    "code": "quota_exceeded",
                    "category": e.category,
                    "limit": e.limit,
                },
                ensure_ascii=False,
            )
            yield f"data: {err}\n\n"
        except ValueError as e:
            err = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        except Exception as e:  # pylint: disable=broad-except
            err = json.dumps(
                {"type": "error", "message": f"服务器内部错误：{e}"}, ensure_ascii=False
            )
            yield f"data: {err}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class DurationUpdate(BaseModel):
    minutes: int


@router.patch("/{session_id}/duration")
def update_duration(
    session_id: str,
    body: DurationUpdate,
    user_id: str = Depends(get_current_user),
):
    """记录本次会话的学习时长（前端离开页面时调用）"""
    try:
        TutorService().record_duration(user_id, session_id, body.minutes)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))
