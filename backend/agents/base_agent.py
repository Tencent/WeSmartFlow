"""
BaseAgent：通用 Agent 基类

所有场景（tutor、extract 等）共用的基础实现：
- stream_chat：流式单轮对话（SSE 场景）
- run：非流式单次运行（后台任务场景）

子类只需继承并添加场景特有方法，无需重复实现基础能力。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from typing import Any, AsyncGenerator

from agent_core.agent.base import AgentStreamEvent
from agent_core.agent.react import ReActAgent

logger = logging.getLogger(__name__)


class BaseAgent(ReActAgent):
    """通用 Agent 基类。

    提供两种运行模式：
    - stream_chat：流式输出，逐步 yield AgentStreamEvent（适合 SSE / 实时对话）
    - run：非流式运行，等待完整结果返回（适合后台任务）

    工具注册、ContextBuilder 组装均由调用方（Service 层或子类）完成。
    """

    async def stream_chat(
        self, user_message: str, **kwargs: Any
    ) -> AsyncGenerator[AgentStreamEvent, None]:
        """流式单轮对话，逐步 yield AgentStreamEvent。

        事件顺序：
        - AgentThinkEvent      — LLM 思考内容
        - AgentToolCallEvent   — 工具调用请求
        - AgentToolResultEvent — 工具执行结果
        - AgentFinalEvent      — 最终回复（结束标志）

        kwargs 透传给 context_builder.build_messages()。
        """
        async for event in self.async_stream(user_message, **kwargs):
            yield event
