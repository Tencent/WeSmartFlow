"""上下文构建器基类。

定义 Agent 系统中上下文构建的统一接口。
子类负责实现具体的 system prompt 拼装和消息列表构建逻辑。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..llm.base import LLMResponse, MessageRole


class BaseContextBuilder(ABC):
    """上下文构建器抽象基类。

    子类需实现：
    - ``build_system_prompt()``：拼装 system prompt 字符串。
    - ``build_messages()``：构建完整的消息列表供 LLM 调用。

    ``build_messages`` 的结构为：
        [system] + history + [user]（user 可选）

    - 传入 ``current_message`` 时：初始化对话或追加新一轮用户输入。
    - 不传 ``current_message`` 时：仅重建 system + history，适用于
      动态 system prompt 需要刷新但不新增用户消息的场景。

    概念约定：
    - ``history``：agent 运行过程中积累的对话记录（不含 system prompt），
      由 agent 内部维护，是 add_* 方法操作的对象。
    - ``messages``：传给 LLM 的完整列表（= system + history + 可选 user），
      由 ``build_messages()`` 负责组装，不在此处维护。

    通用工具方法（直接可用）：
    - ``add_user_message()``：向 history 追加 user 消息。
    - ``add_tool_result()``：向 history 追加工具执行结果。
    - ``add_assistant_message()``：向 history 追加 assistant 消息。
    """

    @abstractmethod
    def build_system_prompt(self, **kwargs: Any) -> str:
        """构建 system prompt 字符串。

        Args:
            **kwargs: 子类自定义的构建参数。

        Returns:
            完整的 system prompt 文本。
        """
        ...

    @abstractmethod
    def build_messages(
        self,
        history: List[Dict[str, Any]] = None,
        current_message: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """构建完整的消息列表。

        结构为 [system] + history + [user]，其中 user 消息可选。

        Args:
            history:         历史对话消息列表（OpenAI 格式 dict）。
            current_message: 本轮用户输入。为 None 时不追加 user 消息，
                             适用于需要刷新 system prompt 但不新增用户
                             消息的场景（如动态 system prompt 延展）。
            **kwargs:        子类自定义的构建参数（如 media、channel 等）。

        Returns:
            OpenAI 格式的消息字典列表，可直接传给 LLM。
        """
        ...

    # ------------------------------------------------------------------
    # 通用工具方法
    # ------------------------------------------------------------------

    def add_user_message(
        self,
        history: List[Dict[str, Any]],
        content: str,
    ) -> List[Dict[str, Any]]:
        """向 history 追加 user 消息。

        Args:
            history: 当前历史消息列表（原地修改，不含 system prompt）。
            content: 用户消息文本。

        Returns:
            追加后的 history。
        """
        history.append(
            {
                "role": MessageRole.USER.value,
                "content": content,
            }
        )
        return history

    def add_tool_result(
        self,
        history: List[Dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: Any,
    ) -> List[Dict[str, Any]]:
        """向 history 追加工具执行结果（role=tool）。

        Args:
            history:      当前历史消息列表（原地修改，不含 system prompt）。
            tool_call_id: 对应 assistant 消息中 tool_call 的 id。
            tool_name:    工具名称。
            result:       工具执行结果，建议为字符串。

        Returns:
            追加后的 history。
        """
        history.append(
            {
                "role": MessageRole.TOOL.value,
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "content": result,
            }
        )
        return history

    def add_assistant_message(
        self,
        history: List[Dict[str, Any]],
        response: LLMResponse,
    ) -> List[Dict[str, Any]]:
        """向 history 追加 assistant 消息。

        从 LLMResponse 中解析 content 和 tool_calls，
        自动组装为 OpenAI 格式的 assistant 消息。

        Args:
            history:  当前历史消息列表（原地修改，不含 system prompt）。
            response: LLM 返回的响应对象。

        Returns:
            追加后的 history。
        """
        msg: Dict[str, Any] = {
            "role": MessageRole.ASSISTANT.value,
            "content": response.content or None,
        }
        if response.has_tool_calls:
            msg["tool_calls"] = [tc.to_openai_tool_call() for tc in response.tool_calls]
        history.append(msg)
        return history
