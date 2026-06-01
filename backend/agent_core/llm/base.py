"""LLM 基础抽象层。

定义消息格式、响应格式和 LLM 抽象基类。
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional, Union

# before_call hook 签名：() -> None 或 Awaitable[None]
BeforeCallHook = Callable[[], Union[None, Awaitable[None]]]


class MessageRole(Enum):
    """消息角色枚举"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCallRequest:
    """LLM 返回的单个工具调用请求。"""

    id: str
    name: str
    arguments: Dict[str, Any]
    index: int = 0

    def to_openai_tool_call(self) -> Dict[str, Any]:
        """序列化为 OpenAI 风格的 tool_call 字典。"""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
            },
        }


@dataclass
class LLMResponse:
    """LLM 响应，包含文本内容和/或工具调用。"""

    content: str
    tool_calls: List[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return bool(self.metadata.get("error"))

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    def __str__(self) -> str:
        return self.content

    def __repr__(self) -> str:
        return f"LLMResponse(content={self.content!r}, is_error={self.is_error})"


# ---------------------------------------------------------------------------
# 流式事件
# ---------------------------------------------------------------------------


@dataclass
class StreamChunkEvent:
    """流式输出的单个文本 chunk 事件。"""

    # 本次 chunk 新增的文本片段
    delta: str
    # 截至本 chunk 已累积的完整文本
    content: str


@dataclass
class ToolCallDeltaEvent:
    """tool_call arguments 分片事件。

    当 arguments 较长时（如生成代码），每收到一个分片就 yield，
    避免调用方长时间静默等待。
    """

    # tool_call 在本次响应中的下标（并行多个 tool_call 时用于区分）
    index: int
    # tool_call id（仅首个分片携带，后续为空字符串）
    id: str
    # 函数名（仅首个分片携带，后续为空字符串）
    name: str
    # 本次分片新增的 arguments 片段（原始 JSON 字符串片段）
    arguments_delta: str
    # 截至本分片已累积的完整 arguments 字符串（未解析的 JSON 字符串）
    arguments_so_far: str


@dataclass
class StreamFinishEvent:
    """流式输出完成事件，直接持有完整的 LLMResponse。"""

    response: LLMResponse

    @property
    def is_error(self) -> bool:
        return self.response.is_error


# 流式事件联合类型
StreamEvent = Union[StreamChunkEvent, ToolCallDeltaEvent, StreamFinishEvent]


class BaseLLM(ABC):
    """LLM 抽象基类。"""

    def __init__(
        self, model_name: str, before_call: BeforeCallHook | None = None, **kwargs: Any
    ):
        self.model_name = model_name
        self._before_call = before_call
        self.default_config: Dict[str, Any] = kwargs
        # 累积工具调用总数，用于计算跨轮次的全局 tool index，保证每轮 index 不重叠
        self.tool_call_count: int = 0

    def _fire_before_call(self) -> None:
        """同步触发 before_call hook（额度检查等）。"""
        if self._before_call is not None:
            ret = self._before_call()
            if asyncio.iscoroutine(ret):
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(ret)
                    else:
                        loop.run_until_complete(ret)
                except RuntimeError:
                    asyncio.run(ret)

    async def _async_fire_before_call(self) -> None:
        """异步触发 before_call hook。"""
        if self._before_call is not None:
            ret = self._before_call()
            if asyncio.iscoroutine(ret):
                await ret

    @abstractmethod
    def think(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """同步调用，返回完整响应。

        Args:
            messages: 对话消息列表，每条为含 role/content 的字典（OpenAI 格式）。
            tools: Function Calling 工具定义列表，格式同 OpenAI tools 参数。
            tool_choice: 工具选择策略，如 "auto"、"none" 或指定函数。
            config: 其他透传给后端 API 的参数（如 temperature、max_tokens 等）。
        """
        ...

    async def async_think(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """异步调用，返回完整响应。默认用线程池包装同步实现。"""
        return await asyncio.to_thread(self.think, messages, tools, tool_choice, config)

    async def stream_think(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """异步流式调用，依次 yield StreamChunkEvent，最后 yield StreamFinishEvent。

        参数与 async_think 保持一致：
            messages:    对话消息列表。
            tools:       Function Calling 工具定义列表。
            tool_choice: 工具选择策略，如 "auto"、"none" 或指定函数。
            config:      其他透传给后端 API 的参数。

        子类应覆盖此方法以提供真正的流式实现；
        默认实现退化为调用 async_think，仅 yield 一个 chunk + finish。
        """
        resp = await self.async_think(
            messages, tools=tools, tool_choice=tool_choice, config=config
        )
        if resp.content:
            yield StreamChunkEvent(delta=resp.content, content=resp.content)
        yield StreamFinishEvent(response=resp)
