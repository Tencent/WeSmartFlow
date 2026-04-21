"""简单上下文构建器。

适用于 system prompt 固定、无需动态拼装的场景。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..llm.base import MessageRole
from .base import BaseContextBuilder


class SimpleContextBuilder(BaseContextBuilder):
    """固定 system prompt 的上下文构建器。

    适合快速使用，不需要动态拼装 system prompt 的场景。

    Example::

        ctx = SimpleContextBuilder("你是一个教育助手。")

        # 初始化对话
        messages = ctx.build_messages([], "帮我解这道题")
        # → [{"role": "system", ...}, {"role": "user", ...}]

        # 刷新 system + 已有历史，不追加新用户消息
        messages = ctx.build_messages(history)
        # → [{"role": "system", ...}, ...history...]
    """

    def __init__(self, system_prompt: str):
        """
        Args:
            system_prompt: 固定的 system prompt 文本。
        """
        self._system_prompt = system_prompt

    def build_system_prompt(self, **kwargs: Any) -> str:
        return self._system_prompt

    def build_messages(
        self,
        history: List[Dict[str, Any]] = None,
        current_message: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """构建消息列表：[system] + history + [user]。

        Args:
            history:         历史对话消息列表。
            current_message: 用户输入，为 None 时不追加 user 消息。

        Returns:
            OpenAI 格式的消息列表。
        """
        if not history:
            history = []
        messages: List[Dict[str, Any]] = [
            {"role": MessageRole.SYSTEM.value, "content": self._system_prompt},
            *history,
        ]
        if current_message is not None:
            messages.append(
                {"role": MessageRole.USER.value, "content": current_message}
            )
        return messages
