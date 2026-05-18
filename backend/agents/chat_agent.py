"""
ChatAgent：流式聊天 Agent

继承 ReActAgent，对外暴露语义化的 ``stream_chat()`` 接口，专为 SSE / 实时对话场景使用。

之所以独立命名 ChatAgent（而非沿用 BaseAgent），是为了避免与
``agent_core.agent.base.BaseAgent``（抽象基类）发生命名冲突，让"业务侧聊天 agent"
与"框架侧抽象基类"在导入时一目了然。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from agent_core.agent.base import AgentStreamEvent
from agent_core.agent.react import ReActAgent

logger = logging.getLogger(__name__)


class ChatAgent(ReActAgent):
    """业务侧通用流式聊天 Agent。

    提供两种运行模式：
    - stream_chat：流式输出，逐步 yield AgentStreamEvent（适合 SSE / 实时对话）
    - run（继承自 ReActAgent）：非流式运行，等待完整结果返回（适合后台任务）

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
