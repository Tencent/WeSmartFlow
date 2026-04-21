"""ReAct Agent 实现。

范式：Reason + Act
每一步：LLM 推理（可能包含 Thought）→ 若有工具调用则执行 → 将结果追加 history → 继续推理
直到 LLM 不再调用工具（输出最终答案）或达到 max_steps。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..context.base import BaseContextBuilder
from ..context.simple import SimpleContextBuilder
from ..llm.base import BaseLLM
from ..tool.registry import ToolRegistry
from .base import (
    AgentFinishReason,
    AgentFinalEvent,
    AgentResult,
    AgentStreamEvent,
    AgentThinkEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    BaseAgent,
)

logger = logging.getLogger(__name__)

# ReActAgent 默认 system prompt
_DEFAULT_REACT_SYSTEM_PROMPT = """你是一个智能助手，能够借助工具逐步解决复杂问题。

## 工作流程

每一步你必须先思考，再决定行动：

Thought: <分析当前情况，明确已知信息、缺少什么、下一步应该做什么>

然后：
- 如果需要更多信息 → 调用合适的工具
- 如果信息已经足够 → 直接给出完整、准确的最终答案

## 规则

1. 每次调用工具前必须先写 Thought，不得省略。
2. 工具结果返回后，继续写 Thought 分析结果，再决定下一步。
3. 不要重复调用已经得到结果的工具。
4. 最终答案要直接回答用户问题，简洁清晰，不要包含 Thought 标记。"""


class ReActAgent(BaseAgent):
    """ReAct 范式 Agent。

    ``context_builder`` 可选，不传时自动使用内置的 ReAct 专用 system prompt。

    循环结构::

        history = [user_message]
        messages = build_messages(history)
        loop (max_steps):
            response = think(messages, tools)
            add_assistant_message(history, response)
            if response.has_tool_calls:
                执行所有工具 → add_tool_result(history, ...)
                messages = build_messages(history)   # 重建，不追加新 user
            else:
                返回 STOP，response.content 即最终答案

    子类可覆写 ``_on_tool_result()`` 在每次工具返回后插入额外逻辑。
    """

    def __init__(
        self,
        llm: BaseLLM,
        context_builder: Optional[BaseContextBuilder] = None,
        tool_registry: Optional[ToolRegistry] = None,
        max_steps: int = 20,
        llm_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            llm:             LLM 实例。
            context_builder: 上下文构建器。为 None 时使用内置 ReAct 专用 prompt。
            tool_registry:   工具注册表，为 None 时表示无工具。
            max_steps:       推理循环最大步数。
            llm_config:      每次调用 LLM 时透传的额外参数（temperature 等）。
        """
        if context_builder is None:
            context_builder = SimpleContextBuilder(_DEFAULT_REACT_SYSTEM_PROMPT)
        super().__init__(
            llm=llm,
            context_builder=context_builder,
            tool_registry=tool_registry,
            max_steps=max_steps,
            llm_config=llm_config,
        )

    def _run(self, user_input: str, **kwargs: Any) -> AgentResult:
        history: List[Dict[str, Any]] = []

        # 将 user 消息加入 history，再构建完整 messages（system + history）
        self.context_builder.add_user_message(history, user_input)
        messages = self.context_builder.build_messages(history, **kwargs)

        tools = self.tool_registry.get_definitions() or None

        for step in range(self.max_steps):
            logger.debug("[ReAct] ── step %d ──", step + 1)

            response = self.think(messages, tools=tools)

            # 打印 Thought（LLM 在工具调用前输出的思考过程）
            if response.content:
                logger.debug("[ReAct] Thought: %s", response.content)

            # 将 assistant 消息追加到 history
            self.context_builder.add_assistant_message(history, response)

            if not response.has_tool_calls:
                logger.debug("[ReAct] 完成，共 %d 步", step + 1)
                return AgentResult(
                    finish_reason=AgentFinishReason.STOP,
                    final_response=response,
                    history=history,
                )

            # 执行所有工具调用，结果追加到 history
            for tc in response.tool_calls:
                logger.debug("[ReAct] Action: %s(%s)", tc.name, tc.arguments)
                result = self.tool_registry.execute(tc.name, tc.arguments)
                logger.debug(
                    "[ReAct] Observation: %s",
                    result[:300] if isinstance(result, str) else result,
                )
                self.context_builder.add_tool_result(history, tc.id, tc.name, result)
                self._on_tool_result(tc.name, tc.arguments, result, history, **kwargs)

            # 重建 messages（system + 更新后的 history，不追加新 user）
            messages = self.context_builder.build_messages(history, **kwargs)

        logger.warning("[ReAct] 达到最大步数 %d，强制结束", self.max_steps)
        return AgentResult(
            finish_reason=AgentFinishReason.MAX_STEPS,
            final_response=None,
            history=history,
        )

    # ------------------------------------------------------------------
    # 异步推理循环
    # ------------------------------------------------------------------

    async def _async_run(self, user_input: str, **kwargs: Any) -> AgentResult:
        """异步版本的 ReAct 推理循环。

        与同步 ``_run()`` 逻辑完全一致，但使用：
        - ``async_think()`` 异步调用 LLM
        - ``tool_registry.async_execute()`` 异步执行工具

        这使得在 IO 密集场景（网络请求、文件读写）下不会阻塞事件循环。
        """
        history: List[Dict[str, Any]] = []

        self.context_builder.add_user_message(history, user_input)
        messages = self.context_builder.build_messages(history, **kwargs)

        tools = self.tool_registry.get_definitions() or None

        for step in range(self.max_steps):
            logger.debug("[ReAct-Async] ── step %d ──", step + 1)

            response = await self.async_think(messages, tools=tools)

            if response.content:
                logger.debug("[ReAct-Async] Thought: %s", response.content)

            self.context_builder.add_assistant_message(history, response)

            if not response.has_tool_calls:
                logger.debug("[ReAct-Async] 完成，共 %d 步", step + 1)
                return AgentResult(
                    finish_reason=AgentFinishReason.STOP,
                    final_response=response,
                    history=history,
                )

            # 执行所有工具调用（顺序执行，保持与同步版一致的语义）
            for tc in response.tool_calls:
                logger.debug("[ReAct-Async] Action: %s(%s)", tc.name, tc.arguments)
                result = await self.tool_registry.async_execute(tc.name, tc.arguments)
                logger.debug(
                    "[ReAct-Async] Observation: %s",
                    result[:300] if isinstance(result, str) else result,
                )
                self.context_builder.add_tool_result(history, tc.id, tc.name, result)
                await self._async_on_tool_result(
                    tc.name, tc.arguments, result, history, **kwargs
                )

            messages = self.context_builder.build_messages(history, **kwargs)

        logger.warning("[ReAct-Async] 达到最大步数 %d，强制结束", self.max_steps)
        return AgentResult(
            finish_reason=AgentFinishReason.MAX_STEPS,
            final_response=None,
            history=history,
        )

    # ------------------------------------------------------------------
    # 扩展钩子
    # ------------------------------------------------------------------

    def _on_tool_result(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: str,
        history: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> None:
        """每次工具执行完成后的同步钩子，子类可覆写。

        Args:
            tool_name:  工具名称。
            arguments:  工具调用参数。
            result:     工具执行结果字符串。
            history:    当前 history（已包含本次 tool result）。
        """

    async def _async_on_tool_result(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: str,
        history: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> None:
        """每次工具执行完成后的异步钩子，子类可覆写。

        默认调用同步版 ``_on_tool_result()``。

        Args:
            tool_name:  工具名称。
            arguments:  工具调用参数。
            result:     工具执行结果字符串。
            history:    当前 history（已包含本次 tool result）。
        """
        self._on_tool_result(tool_name, arguments, result, history, **kwargs)

    # ------------------------------------------------------------------
    # 流式推理（异步生成器）
    # ------------------------------------------------------------------

    async def async_stream(
        self, user_input: str, **kwargs: Any
    ) -> AsyncGenerator[AgentStreamEvent, None]:
        """异步流式推理，每个关键节点 yield 一个事件。

        事件类型（按发生顺序）：
        - AgentThinkEvent      — LLM 返回了思考内容（含 Thought 文本）
        - AgentToolCallEvent   — 即将调用某个工具
        - AgentToolResultEvent — 工具执行完毕
        - AgentFinalEvent      — 最终回复（推理结束）

        Args:
            user_input: 用户输入文本。
            **kwargs:   透传给 context_builder.build_messages() 的额外参数。

        Yields:
            AgentStreamEvent
        """
        history: List[Dict[str, Any]] = []
        self.context_builder.add_user_message(history, user_input)
        messages = self.context_builder.build_messages(history, **kwargs)
        tools = self.tool_registry.get_definitions() or None

        for step in range(1, self.max_steps + 1):
            logger.debug("[ReAct-Stream] ── step %d ──", step)

            response = await self.async_think(messages, tools=tools)

            # yield 思考内容（即使为空字符串也 yield，让调用方感知到 LLM 已响应）
            if response.content:
                yield AgentThinkEvent(content=response.content, step=step)

            self.context_builder.add_assistant_message(history, response)

            if not response.has_tool_calls:
                # 最终回复
                logger.debug("[ReAct-Stream] 完成，共 %d 步", step)
                yield AgentFinalEvent(
                    content=response.content,
                    finish_reason=AgentFinishReason.STOP,
                )
                return

            # 逐个执行工具调用
            for tc in response.tool_calls:
                yield AgentToolCallEvent(
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    step=step,
                )
                logger.debug("[ReAct-Stream] Action: %s(%s)", tc.name, tc.arguments)

                result = await self.tool_registry.async_execute(tc.name, tc.arguments)
                logger.debug(
                    "[ReAct-Stream] Observation: %s",
                    result[:300] if isinstance(result, str) else result,
                )

                yield AgentToolResultEvent(
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    result=result if isinstance(result, str) else str(result),
                    step=step,
                )

                self.context_builder.add_tool_result(history, tc.id, tc.name, result)
                await self._async_on_tool_result(
                    tc.name, tc.arguments, result, history, **kwargs
                )

            messages = self.context_builder.build_messages(history, **kwargs)

        logger.warning("[ReAct-Stream] 达到最大步数 %d，强制结束", self.max_steps)
        yield AgentFinalEvent(
            content="",
            finish_reason=AgentFinishReason.MAX_STEPS,
        )
