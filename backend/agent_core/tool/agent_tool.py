"""Agent-as-Tool 包装器。

将任意 BaseAgent 包装为 BaseTool，使其可以被父 Agent 当作工具调用，
实现多 Agent 层级协作（Orchestrator → Sub-Agent）。

推荐通过 ``BaseAgent.as_tool()`` 快捷方法创建，而非直接实例化。

用法示例::

    # 创建子 Agent
    researcher = ReActAgent(llm=llm, tool_registry=search_tools)

    # 包装为工具
    researcher_tool = researcher.as_tool(
        name="researcher",
        description="负责信息检索和资料收集的子 Agent，输入研究问题，返回调研结果。",
    )

    # 注册到父 Agent
    orchestrator = PlanAndSolveAgent(
        llm=llm,
        tool_registry=ToolRegistry([researcher_tool, writer_tool]),
    )
    result = orchestrator.run("写一篇关于量子计算的综述")
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from .base import BaseTool

if TYPE_CHECKING:
    from ..agent.base import BaseAgent

logger = logging.getLogger(__name__)


class AgentTool(BaseTool):
    """将一个 BaseAgent 包装为 BaseTool，供父 Agent 作为工具调用。

    核心行为：
    - 父 Agent 通过 Function Calling 传入 ``input`` 参数
    - AgentTool 调用子 Agent 的 ``run()`` 方法
    - 将子 Agent 的 ``AgentResult.output`` 作为工具结果返回

    参数说明：
    - ``input``: 传递给子 Agent 的问题或指令（必填）
    - ``context``: 可选的额外上下文信息，会拼接在 input 之前

    错误处理：
    - 子 Agent 运行异常时，返回错误信息字符串（不抛异常），
      让父 Agent 有机会分析错误并决定下一步行动。
    """

    def __init__(
        self,
        agent: "BaseAgent",
        name: str,
        description: str,
        run_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            agent:       被包装的子 Agent 实例。
            name:        工具名称，供父 Agent 在 Function Calling 中识别。
            description: 工具描述，告知父 Agent 何时调用、输入什么。
            run_kwargs:  每次调用子 Agent 时透传的额外关键字参数
                         （如 channel、media 等 context_builder 需要的参数）。
        """
        self._agent = agent
        self._run_kwargs = run_kwargs or {}

        super().__init__(
            name=name,
            description=description,
            parameters={
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "传递给子 Agent 的问题或指令",
                    },
                    "context": {
                        "type": "string",
                        "description": "可选的额外上下文信息，会拼接在 input 之前提供给子 Agent",
                    },
                },
                "required": ["input"],
            },
        )

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def agent(self) -> "BaseAgent":
        """获取被包装的子 Agent 实例。"""
        return self._agent

    # ------------------------------------------------------------------
    # 同步执行
    # ------------------------------------------------------------------

    def run(self, input: str, context: str = "", **kwargs: Any) -> str:  # noqa: A002
        """调用子 Agent 并返回其最终输出文本。

        Args:
            input:   传递给子 Agent 的问题或指令。
            context: 可选的额外上下文，非空时拼接在 input 之前。

        Returns:
            str: 子 Agent 的最终答案文本。
        """
        user_input = f"{context}\n\n{input}" if context else input

        logger.info(
            "[AgentTool] 委派任务给子 Agent '%s': %s",
            self.name,
            user_input[:200],
        )

        try:
            result = self._agent.run(user_input, **self._run_kwargs)
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("[AgentTool] 子 Agent '%s' 运行异常", self.name)
            return f"Error: 子 Agent '{self.name}' 执行失败: {e}"

        output = result.output
        logger.info(
            "[AgentTool] 子 Agent '%s' 完成 (reason=%s): %s",
            self.name,
            result.finish_reason.value,
            output[:200],
        )
        return output

    # ------------------------------------------------------------------
    # 异步执行
    # ------------------------------------------------------------------

    async def async_run(self, input: str, context: str = "", **kwargs: Any) -> str:  # noqa: A002
        """异步调用子 Agent 并返回其最终输出文本。

        Args:
            input:   传递给子 Agent 的问题或指令。
            context: 可选的额外上下文，非空时拼接在 input 之前。

        Returns:
            str: 子 Agent 的最终答案文本。
        """
        user_input = f"{context}\n\n{input}" if context else input

        logger.info(
            "[AgentTool] 异步委派任务给子 Agent '%s': %s",
            self.name,
            user_input[:200],
        )

        try:
            result = await self._agent.async_run(user_input, **self._run_kwargs)
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("[AgentTool] 子 Agent '%s' 异步运行异常", self.name)
            return f"Error: 子 Agent '{self.name}' 执行失败: {e}"

        output = result.output
        logger.info(
            "[AgentTool] 子 Agent '%s' 异步完成 (reason=%s): %s",
            self.name,
            result.finish_reason.value,
            output[:200],
        )
        return output

    # ------------------------------------------------------------------
    # 表示
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<AgentTool name={self.name!r} agent={self._agent.__class__.__name__}>"
