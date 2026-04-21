"""
会话路由（含 SSE 流式聊天）
"""

from __future__ import annotations

import asyncio
import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from database import get_db_dep
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

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

USER_ID = "default"


@router.get("", response_model=list[SessionSchema])
def list_sessions(db: sqlite3.Connection = Depends(get_db_dep)):
    return TutorService(db).session_repo.get_all(USER_ID)


@router.post("", response_model=SessionSchema, status_code=201)
def create_session(data: SessionCreate, db: sqlite3.Connection = Depends(get_db_dep)):
    return TutorService(db).create_session(USER_ID, data)


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, db: sqlite3.Connection = Depends(get_db_dep)):
    detail = TutorService(db).session_repo.get_detail(session_id)
    if not detail:
        raise HTTPException(404, "会话不存在")
    return detail


@router.post("/{session_id}/chat/stream")
async def chat_stream(
    request: Request,
    session_id: str,
    body: ChatMessage,
    db: sqlite3.Connection = Depends(get_db_dep),
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
    service = TutorService(db)
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _serialize(event) -> str | None:
        """将 Agent 事件序列化为 SSE data 行。"""
        if isinstance(event, AgentThinkEvent):
            data = {"type": "thinking", "content": event.content, "step": event.step}
        elif isinstance(event, AgentToolCallEvent):
            data = {
                "type": "tool_call",
                "tool": event.tool_name,
                "args": event.arguments,
                "step": event.step,
            }
        elif isinstance(event, AgentToolResultEvent):
            data = {
                "type": "tool_result",
                "tool": event.tool_name,
                "result": event.result,
                "step": event.step,
            }
        elif isinstance(event, AgentFinalEvent):
            return None  # 特殊处理，见下方
        elif isinstance(event, FileCreatedEvent):
            data = {"type": "file_created", "file_id": event.file_id}
        elif isinstance(event, NodeCreatedEvent):
            data = {
                "type": "node_created",
                "node_id": event.node_id,
                "title": event.title,
            }
        elif isinstance(event, MasteryUpdatedEvent):
            data = {
                "type": "mastery_updated",
                "node_id": event.node_id,
                "delta": event.delta,
            }
        else:
            return None
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def produce():
        """在后台 task 中运行 Agent，把 SSE 行放入队列，结束时放入 None 哨兵。"""
        mastery_changes: dict[str, float] = {}
        try:
            async for event in service.stream_chat(USER_ID, session_id, body.content):
                if isinstance(event, MasteryUpdatedEvent):
                    mastery_changes[event.node_id] = (
                        mastery_changes.get(event.node_id, 0.0) + event.delta
                    )
                if isinstance(event, AgentFinalEvent):
                    text_data = json.dumps(
                        {"type": "text_reply", "text": event.content},
                        ensure_ascii=False,
                    )
                    await queue.put(f"data: {text_data}\n\n")
                    done_data = json.dumps(
                        {"type": "done", "mastery_changes": mastery_changes},
                        ensure_ascii=False,
                    )
                    await queue.put(f"data: {done_data}\n\n")
                else:
                    line = _serialize(event)
                    if line:
                        await queue.put(line)
        except asyncio.CancelledError:
            pass  # 客户端断开，静默退出
        except ValueError as e:
            err = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
            await queue.put(f"data: {err}\n\n")
        except Exception as e:  # pylint: disable=broad-except
            err = json.dumps(
                {"type": "error", "message": f"服务器内部错误：{e}"}, ensure_ascii=False
            )
            await queue.put(f"data: {err}\n\n")
        finally:
            await queue.put(None)  # 哨兵，通知消费方结束

    async def event_generator():
        task = asyncio.create_task(produce())
        try:
            while True:
                # 用超时轮询方式：每次最多等 0.3s，期间检查客户端是否断开
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.3)
                except asyncio.TimeoutError:
                    # 队列暂时没数据，检查客户端是否断开
                    if await request.is_disconnected():
                        task.cancel()
                        break
                    continue

                if item is None:
                    break  # 哨兵，正常结束
                yield item
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # pylint: disable=broad-except
                pass

    return StreamingResponse(
        event_generator(),
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
    session_id: str, body: DurationUpdate, db: sqlite3.Connection = Depends(get_db_dep)
):
    """记录本次会话的学习时长（前端离开页面时调用）"""
    try:
        TutorService(db).record_duration(USER_ID, session_id, body.minutes)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))
