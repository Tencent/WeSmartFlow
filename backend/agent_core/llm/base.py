"""LLM 基础抽象层。

定义消息格式、响应格式和 LLM 抽象基类。
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

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


class BaseLLM(ABC):
    """LLM 抽象基类。"""

    def __init__(
        self, model_name: str, before_call: BeforeCallHook | None = None, **kwargs: Any
    ):
        self.model_name = model_name
        self._before_call = before_call
        self.default_config: Dict[str, Any] = kwargs

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
