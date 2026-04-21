"""LLM 基础抽象层。

定义消息格式、响应格式和 LLM 抽象基类。
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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

    def __init__(self, model_name: str, **kwargs: Any):
        self.model_name = model_name
        self.default_config: Dict[str, Any] = kwargs

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
