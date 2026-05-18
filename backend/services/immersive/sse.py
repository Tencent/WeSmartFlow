"""SSE 事件序列化与 Agent 事件流转发。

把原本散落在主流程里 4 处几乎完全相同的"agent.async_stream → SSE 事件"
转发模板抽成单一函数 `stream_agent_events`，消除重复。
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, List, Optional

from agent_core.agent import (
    AgentFinalEvent,
    AgentThinkEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    ReActAgent,
)


def sse_event(type: str, **data) -> str:
    """构造单条 SSE 消息（已含末尾的双换行）。"""
    payload = {"type": type, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_agent_events(
    agent: ReActAgent,
    prompt: str,
    agent_type: str,
    *,
    skill_names: Optional[List[str]] = None,
    start_msg: str = "",
    finish_msg: str = "完成",
) -> AsyncGenerator[str, None]:
    """运行 agent 并把内部事件统一转换成 SSE 字符串。

    Args:
        agent: ReActAgent 实例
        prompt: 用户 prompt
        agent_type: SSE 事件中的 agent_type 字段（planner / researcher / ...）
        skill_names: 传给 agent.async_stream 的技能名列表
        start_msg: 起始事件的 content
        finish_msg: AgentFinalEvent 对应 SSE 事件的 content
    """
    yield sse_event(
        "agent_event",
        agent_type=agent_type,
        event_type="start",
        content=start_msg,
        step=0,
    )

    async for event in agent.async_stream(prompt, skill_names=skill_names or []):
        if isinstance(event, AgentThinkEvent):
            yield sse_event(
                "agent_event",
                agent_type=agent_type,
                event_type="think",
                content=event.content,
                step=event.step,
            )
        elif isinstance(event, AgentToolCallEvent):
            yield sse_event(
                "agent_event",
                agent_type=agent_type,
                event_type="tool_call",
                content=f"调用工具 {event.tool_name}: {event.arguments}",
                step=event.step,
            )
        elif isinstance(event, AgentToolResultEvent):
            yield sse_event(
                "agent_event",
                agent_type=agent_type,
                event_type="tool_result",
                content=f"工具 {event.tool_name} 执行完成",
                step=event.step,
            )
        elif isinstance(event, AgentFinalEvent):
            yield sse_event(
                "agent_event",
                agent_type=agent_type,
                event_type="finish",
                content=finish_msg,
                step=0,
            )
