"""Agent 抽象基类。

只定义骨架：依赖注入 + 运行入口 + 通用工具方法。
具体的推理范式（ReAct / Plan-and-Solve / Reflection 等）由子类实现 ``_run()``。
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ..context.base import BaseContextBuilder
from ..llm.base import BaseLLM, LLMResponse
from ..tool.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================


class AgentFinishReason(Enum):
    """Agent 结束原因。"""

    STOP = "stop"  # 正常结束
    MAX_STEPS = "max_steps"  # 达到最大步数
    ERROR = "error"  # 运行时错误


# ============================================================
# 流式事件类型
# ============================================================


@dataclass
class AgentThinkEvent:
    """LLM 返回了思考内容（Thought），可能伴随工具调用请求。"""

    content: str  # LLM 输出的文本（Thought / 中间推理）
    step: int  # 当前推理步数（从 1 开始）


@dataclass
class AgentToolCallEvent:
    """Agent 即将调用某个工具。"""

    tool_name: str
    arguments: Dict[str, Any]
    step: int


@dataclass
class AgentToolResultEvent:
    """工具执行完毕，返回结果。"""

    tool_name: str
    arguments: Dict[str, Any]
    result: str
    step: int


@dataclass
class AgentFinalEvent:
    """Agent 推理结束，产出最终回复。"""

    content: str
    finish_reason: AgentFinishReason


# ============================================================
# 业务语义事件（由工具 hook 触发，可直接推送给前端）
# ============================================================


@dataclass
class FileCreatedEvent:
    """文件（PDF 卡片等）生成完毕。"""

    file_id: str  # 相对路径，如 "{uuid}.pdf"


@dataclass
class NodeCreatedEvent:
    """知识节点被创建。"""

    node_id: str
    title: str


@dataclass
class MasteryUpdatedEvent:
    """节点掌握度发生变化。"""

    node_id: str
    delta: float  # 本次变化量


# 所有流式事件的联合类型
AgentStreamEvent = Union[
    AgentThinkEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    AgentFinalEvent,
    FileCreatedEvent,
    NodeCreatedEvent,
    MasteryUpdatedEvent,
]


@dataclass
class AgentResult:
    """Agent 完整运行结果。"""

    finish_reason: AgentFinishReason
    final_response: Optional[LLMResponse]
    history: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def output(self) -> str:
        """最终输出文本，出错时返回错误信息。"""
        if self.error:
            return f"[Error] {self.error}"
        return self.final_response.content if self.final_response else ""


# ============================================================
# BaseAgent
# ============================================================


class BaseAgent(ABC):
    """Agent 抽象基类。

    职责：
    - 持有三个核心依赖（llm / context_builder / tool_registry）
    - 提供统一的 ``run`` / ``async_run`` 入口（负责异常捕获和结果封装）
    - 提供通用工具方法（``think`` / ``execute_tool_calls``）供子类复用

    子类必须实现：
    - ``_run()``：完整的推理循环，返回 AgentResult。
      不同范式（ReAct / Plan-and-Solve / Reflection）在此各自实现。
    """

    def __init__(
        self,
        llm: BaseLLM,
        context_builder: BaseContextBuilder,
        tool_registry: Optional[ToolRegistry] = None,
        max_steps: int = 20,
        llm_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            llm:             LLM 实例。
            context_builder: 上下文构建器实例。
            tool_registry:   工具注册表，为 None 时表示无工具。
            max_steps:       子类推理循环的最大步数上限，防止死循环。
            llm_config:      每次调用 LLM 时透传的额外参数（temperature 等）。
        """
        self.llm = llm
        self.context_builder = context_builder
        self.tool_registry = tool_registry or ToolRegistry()
        self.max_steps = max_steps
        self.llm_config = llm_config or {}

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------

    def run(self, user_input: str, **kwargs: Any) -> AgentResult:
        """同步运行 Agent。

        负责调用 ``_run()`` 并统一捕获异常。

        Args:
            user_input: 用户输入文本。
            **kwargs:   透传给子类 ``_run()`` 的额外参数。

        Returns:
            AgentResult
        """
        try:
            return self._run(user_input, **kwargs)
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Agent 运行异常")
            return AgentResult(
                finish_reason=AgentFinishReason.ERROR,
                final_response=None,
                error=str(e),
            )

    async def async_run(self, user_input: str, **kwargs: Any) -> AgentResult:
        """异步运行 Agent。

        若子类实现了 ``_async_run()``，则调用真正的异步推理循环；
        否则回退到线程池包装同步 ``run()``。

        Args:
            user_input: 用户输入文本。
            **kwargs:   透传给子类的额外参数。

        Returns:
            AgentResult
        """
        try:
            return await self._async_run(user_input, **kwargs)
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Agent 异步运行异常")
            return AgentResult(
                finish_reason=AgentFinishReason.ERROR,
                final_response=None,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # 子类必须实现
    # ------------------------------------------------------------------

    @abstractmethod
    def _run(self, user_input: str, **kwargs: Any) -> AgentResult:
        """同步推理主循环，由子类实现具体范式。

        Args:
            user_input: 用户输入文本。
            **kwargs:   子类自定义的额外参数。

        Returns:
            AgentResult
        """
        ...

    async def _async_run(self, user_input: str, **kwargs: Any) -> AgentResult:
        """异步推理主循环，子类可覆写以实现真正的异步推理。

        默认回退到线程池包装同步 ``_run()``。
        子类（如 ReActAgent）可覆写此方法，使用 ``async_think`` +
        ``tool_registry.async_execute`` 实现全链路异步。

        Args:
            user_input: 用户输入文本。
            **kwargs:   子类自定义的额外参数。

        Returns:
            AgentResult
        """
        return await asyncio.to_thread(self._run, user_input, **kwargs)

    # ------------------------------------------------------------------
    # 通用工具方法（子类可直接调用）
    # ------------------------------------------------------------------

    def think(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
    ) -> LLMResponse:
        """同步调用 LLM 推理，返回 LLMResponse。

        Args:
            messages:    传给 LLM 的完整消息列表（= system + history + 可选 user），
                         由 ``context_builder.build_messages()`` 组装，不要直接传 history。
            tools:       工具 schema 列表，为 None 时不传工具。
            tool_choice: 工具选择策略，如 "auto"、"none" 或指定函数。
                         Reflect 等不需要工具的阶段可传 "none" 禁止工具调用。

        Returns:
            LLMResponse
        """
        return self.llm.think(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            config=self.llm_config or None,
        )

    async def async_think(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
    ) -> LLMResponse:
        """异步调用 LLM 推理，返回 LLMResponse。

        Args:
            messages:    传给 LLM 的完整消息列表。
            tools:       工具 schema 列表，为 None 时不传工具。
            tool_choice: 工具选择策略。

        Returns:
            LLMResponse
        """
        return await self.llm.async_think(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            config=self.llm_config or None,
        )

    # ------------------------------------------------------------------
    # Agent-as-Tool
    # ------------------------------------------------------------------

    def as_tool(
        self,
        name: str,
        description: str,
        run_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """将当前 Agent 包装为一个 AgentTool，供父 Agent 作为工具调用。

        这是实现多 Agent 层级协作的核心方法：任意 Agent 都可以通过
        ``as_tool()`` 变成一个工具，注册到父 Agent 的 ToolRegistry 中。

        用法示例::

            sub_agent = ReActAgent(llm=llm, tool_registry=sub_tools)
            tool = sub_agent.as_tool(
                name="researcher",
                description="负责信息检索的子 Agent",
            )
            parent = PlanAndSolveAgent(
                llm=llm,
                tool_registry=ToolRegistry([tool]),
            )

        Args:
            name:        工具名称，供父 Agent 在 Function Calling 中识别。
            description: 工具描述，告知父 Agent 何时调用、输入什么。
            run_kwargs:  每次调用子 Agent 时透传的额外关键字参数。

        Returns:
            AgentTool 实例。
        """
        from ..tool.agent_tool import AgentTool

        return AgentTool(
            agent=self,
            name=name,
            description=description,
            run_kwargs=run_kwargs,
        )

    # ------------------------------------------------------------------
    # 魔术方法
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"llm={self.llm.model_name!r} "
            f"tools={self.tool_registry.tool_names}>"
        )
