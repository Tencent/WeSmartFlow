"""
工具注册中心 (ToolRegistry)

负责工具的注册、查找、执行和批量管理。
参考 new_core/tools/registry.py 的设计，增加：
- 批量注册 (register_many)
- 同步/异步双模式执行
- 错误提示引导 LLM 重试
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from ..agent.events import AgentToolResultEvent, AgentToolRunEvent
from .base import BaseTool

logger = logging.getLogger(__name__)

# 追加在错误信息末尾，引导 LLM 换个方式重试
_HINT = "\n\n[请分析上述错误并尝试其他方式。]"


class ToolRegistry:
    """
    工具注册中心，管理所有可用工具。

    功能：
    - 注册 / 注销 / 查找工具
    - 获取所有工具的 OpenAI Function Calling 定义
    - 同步 / 异步执行工具调用
    """

    def __init__(self, tools: Optional[List[BaseTool]] = None):
        self._tools: Dict[str, BaseTool] = {}
        if tools:
            self.register_many(tools)

    # ------------------------------------------------------------------
    # 注册 / 注销
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> BaseTool:
        """
        注册一个工具。

        Args:
            tool: 工具实例

        Returns:
            注册的工具实例（方便链式调用）
        """
        if tool.name in self._tools:
            logger.warning("工具 '%s' 已存在，将被覆盖", tool.name)
        self._tools[tool.name] = tool
        logger.debug("注册工具: %s", tool.name)
        return tool

    def register_many(self, tools: List[BaseTool]) -> None:
        """批量注册工具。"""
        for t in tools:
            self.register(t)

    def unregister(self, name: str) -> None:
        """移除一个工具。"""
        self._tools.pop(name, None)
        logger.debug("注销工具: %s", name)

    # ------------------------------------------------------------------
    # 查找
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[BaseTool]:
        """根据名称获取工具，不存在返回 None。"""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """判断工具是否已注册。"""
        return name in self._tools

    def list_tools(self) -> List[BaseTool]:
        """返回所有已注册的工具列表。"""
        return list(self._tools.values())

    @property
    def tool_names(self) -> List[str]:
        """获取所有已注册工具的名称列表。"""
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # Schema 输出
    # ------------------------------------------------------------------

    def get_definitions(self) -> List[Dict[str, Any]]:
        """
        获取所有工具的 OpenAI tools 格式 JSON Schema。

        Returns::

            [{"type": "function", "function": {...}}, ...]
        """
        return [tool.to_schema() for tool in self._tools.values()]

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    def execute(self, name: str, params: Dict[str, Any]) -> str:
        """
        同步执行一个工具调用。

        Args:
            name: 工具名称
            params: 工具调用参数

        Returns:
            str: 工具执行结果（字符串化）
        """
        tool = self._tools.get(name)
        if not tool:
            return f"Error: 未找到工具 '{name}'，可用工具: {', '.join(self.tool_names)}"

        try:
            result = tool(**params)
            return self._stringify_result(result, name)
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("工具 %s 执行失败", name)
            return f"Error: 工具 {name} 执行失败: {e}" + _HINT

    async def async_stream_execute(
        self,
        tc_id: str,
        name: str,
        params: Dict[str, Any],
        step: int,
        index: int = 0,
    ):
        """
        异步流式执行工具。

        - 每个 chunk 实时 yield AgentToolRunEvent（过程事件，零滞后）
        - 所有 chunk 结束后额外 yield 一次 AgentToolResultEvent（终态标记）

        Args:
            tc_id:  tool_call id。
            name:   工具名称。
            params: 工具调用参数。
            step:   当前推理步数。
            index:  该工具调用在本轮 tool_calls 中的顺序（从 0 开始）。

        Yields:
            AgentToolRunEvent | AgentToolResultEvent
        """
        tool = self._tools.get(name)
        if not tool:
            yield AgentToolResultEvent(
                id=tc_id,
                tool_name=name,
                arguments=params,
                step=step,
                result=f"Error: 未找到工具 '{name}'，可用工具: {', '.join(self.tool_names)}"
                + _HINT,
                index=index,
            )
            return

        try:
            logger.warning(
                "[ToolRegistry] 工具 %s 收到参数 type=%s, value=%r",
                name,
                type(params).__name__,
                params,
            )
            casted = tool.cast_params(params)

            # 执行前 hook
            if tool._before_call_hook is not None:
                ret = tool._before_call_hook()
                if asyncio.iscoroutine(ret):
                    await ret

            # 流式执行（validate_params 由 async_stream_call 统一处理）
            last_chunk = None
            async for chunk in tool.async_stream_call(**params):
                yield AgentToolRunEvent(
                    id=tc_id, tool_name=name, step=step, content=chunk, index=index
                )
                last_chunk = chunk

            result = last_chunk if last_chunk is not None else ""

            # 触发结果 hook
            if tool._on_result_hook is not None:
                ret = tool._on_result_hook(name, casted, result, index)
                if asyncio.iscoroutine(ret):
                    await ret

            # 额外 yield ToolResultEvent 标记终态
            yield AgentToolResultEvent(
                id=tc_id,
                tool_name=name,
                arguments=casted,
                step=step,
                result=result,
                index=index,
            )

        except ValueError as e:
            # async_stream_call 内部参数校验失败会抛 ValueError
            yield AgentToolResultEvent(
                id=tc_id,
                tool_name=name,
                arguments=params,
                step=step,
                result=f"Error: {e}" + _HINT,
                index=index,
            )
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("工具 %s 流式执行失败", name)
            yield AgentToolResultEvent(
                id=tc_id,
                tool_name=name,
                arguments=params,
                step=step,
                result=f"Error: 工具 {name} 执行失败: {e}" + _HINT,
                index=index,
            )

    async def async_execute(self, name: str, params: Dict[str, Any]) -> str:
        """
        异步执行一个工具调用。

        Args:
            name: 工具名称
            params: 工具调用参数

        Returns:
            str: 工具执行结果（字符串化）
        """
        tool = self._tools.get(name)
        if not tool:
            return f"Error: 未找到工具 '{name}'，可用工具: {', '.join(self.tool_names)}"

        try:
            result = await tool.async_call(**params)
            return self._stringify_result(result, name)
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("工具 %s 执行失败", name)
            return f"Error: 工具 {name} 执行失败: {e}" + _HINT

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _stringify_result(result: Any, tool_name: str) -> str:
        """将工具执行结果转换为字符串。"""
        if isinstance(result, str):
            # 如果结果以 Error 开头，追加提示
            if result.startswith("Error"):
                return result + _HINT
            return result
        try:
            return json.dumps(result, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(result)

    # ------------------------------------------------------------------
    # 魔术方法
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __repr__(self) -> str:
        tools = ", ".join(self._tools.keys())
        return f"<ToolRegistry tools=[{tools}]>"
