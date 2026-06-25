"""Plan-and-Solve Agent 实现。

范式：Plan → Execute（+ Replan） → Synthesize

1. Planner:    LLM 将目标拆解为有序步骤列表（Step 对象，带状态）
2. Executor:   逐步执行每个 PENDING 步骤，内部支持工具调用（ReAct 小循环）
3. Replan:     若某步骤失败，保留已完成步骤，重新规划剩余步骤（可配置开关）
4. Synthesize: 汇总所有 DONE 步骤结果，生成最终答案

所有阶段统一通过 context_builder + history 管理消息，
context_builder 的 system prompt 定义 Agent 角色，
history 负责在各阶段之间传递上下文。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ..context.base import BaseContextBuilder
from ..context.simple import SimpleContextBuilder
from ..llm.base import BaseLLM, LLMResponse
from ..tool.registry import ToolRegistry
from .base import AgentResult, BaseAgent
from .events import AgentFinishReason

logger = logging.getLogger(__name__)


# ── 数据结构 ──────────────────────────────────────────────────────────────────


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Step:
    """计划中的单个执行步骤。"""

    id: int
    description: str
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Plan:
    """完整执行计划，驱动主循环。"""

    goal: str
    steps: List[Step] = field(default_factory=list)

    @property
    def pending_steps(self) -> List[Step]:
        return [s for s in self.steps if s.status == StepStatus.PENDING]

    @property
    def done_steps(self) -> List[Step]:
        return [s for s in self.steps if s.status == StepStatus.DONE]

    @property
    def failed_steps(self) -> List[Step]:
        return [s for s in self.steps if s.status == StepStatus.FAILED]

    def summary(self) -> str:
        icon_map = {
            StepStatus.PENDING: "⬜",
            StepStatus.RUNNING: "🔄",
            StepStatus.DONE: "✅",
            StepStatus.FAILED: "❌",
        }
        lines = [f"目标: {self.goal}", "步骤:"]
        for s in self.steps:
            icon = icon_map[s.status]
            hint = ""
            if s.result:
                hint = (
                    f" → {s.result[:80]}..." if len(s.result) > 80 else f" → {s.result}"
                )
            elif s.error:
                hint = f" → ❌ {s.error}"
            lines.append(f"  {icon} [{s.id}] {s.description}{hint}")
        return "\n".join(lines)

    def completed_context(self) -> str:
        """已完成步骤的摘要文本，供后续步骤参考。"""
        done = self.done_steps
        if not done:
            return "（暂无已完成步骤）"
        return "\n".join(
            f"[{s.id}] {s.description}\n    结果: {s.result}" for s in done
        )


# ── 默认 system prompt ────────────────────────────────────────────────────────

_DEFAULT_SYSTEM_PROMPT = """你是一个善于分解问题、逐步执行的智能助手。

你的工作流程：
1. 收到目标后，先将其拆解为 2~8 个清晰、可执行的子步骤
2. 逐步执行每个子步骤，必要时调用工具获取信息
3. 所有步骤完成后，整合结果给出最终答案

执行过程中如遇到步骤失败，会自动重新规划剩余步骤。"""


# ── Agent 实现 ────────────────────────────────────────────────────────────────


class PlanAndSolveAgent(BaseAgent):
    """Plan-and-Solve 范式 Agent。

    执行流程::

        1. plan:      LLM 将目标拆解为 Step 列表（带状态）
        2. execute:   while pending_steps: 执行当前步骤（内部 ReAct 小循环）
        3. replan:    步骤失败时，保留已完成步骤，重新规划剩余步骤（可开关）
        4. synthesize: 汇总所有 DONE 步骤结果，生成最终答案

    所有阶段统一通过 context_builder + history 管理消息，
    不同阶段通过向 history 追加消息来传递上下文。
    """

    def __init__(
        self,
        llm: BaseLLM,
        context_builder: Optional[BaseContextBuilder] = None,
        tool_registry: Optional[ToolRegistry] = None,
        max_steps: int = 20,
        max_steps_per_task: int = 5,
        max_replan: int = 2,
        enable_replan: bool = True,
        llm_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            llm:               LLM 实例。
            context_builder:   上下文构建器，为 None 时使用内置默认。
            tool_registry:     工具注册表。
            max_steps:         子任务数量上限。
            max_steps_per_task: 每个子任务内部工具调用的最大轮次。
            max_replan:        最大重新规划次数。
            enable_replan:     是否启用重新规划。
            llm_config:        透传给 LLM 的额外参数。
        """
        super().__init__(
            llm=llm,
            context_builder=context_builder
            or SimpleContextBuilder(_DEFAULT_SYSTEM_PROMPT),
            tool_registry=tool_registry,
            max_steps=max_steps,
            llm_config=llm_config,
        )
        self.max_steps_per_task = max_steps_per_task
        self.max_replan = max_replan
        self.enable_replan = enable_replan

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def _run(self, user_input: str, **kwargs: Any) -> AgentResult:
        tools = self.tool_registry.get_definitions() or None
        replan_count = 0

        # 整个 Agent 共用一个 history，各阶段通过追加消息传递上下文
        history: List[Dict[str, Any]] = []

        # ── 阶段一：Plan ──────────────────────────────────────────────
        plan = self._plan(user_input, history, **kwargs)
        logger.debug(
            "[PlanAndSolve] 计划生成，共 %d 步:\n%s", len(plan.steps), plan.summary()
        )

        # ── 阶段二：Execute（+ Replan）────────────────────────────────
        while plan.pending_steps:
            step = plan.pending_steps[0]
            logger.debug(
                "[PlanAndSolve] ── 执行步骤 [%d]: %s", step.id, step.description
            )
            self._execute_step(step, plan, history, tools, **kwargs)

            if step.status == StepStatus.FAILED and self.enable_replan:
                if replan_count < self.max_replan:
                    replan_count += 1
                    logger.debug(
                        "[PlanAndSolve] 步骤 [%d] 失败，触发第 %d 次重新规划",
                        step.id,
                        replan_count,
                    )
                    self._replan(plan, failed_step=step, history=history, **kwargs)
                else:
                    logger.warning(
                        "[PlanAndSolve] 已达最大重新规划次数 (%d)，跳过失败步骤继续",
                        self.max_replan,
                    )

        logger.debug("[PlanAndSolve] 执行完毕:\n%s", plan.summary())

        # ── 阶段三：Synthesize ────────────────────────────────────────
        final_response = self._synthesize(plan, history, **kwargs)
        logger.debug("[PlanAndSolve] 最终答案: %s", final_response.content[:200])

        return AgentResult(
            finish_reason=AgentFinishReason.STOP,
            final_response=final_response,
            history=history,
            metadata={
                "plan_summary": plan.summary(),
                "total_steps": len(plan.steps),
                "done_steps": len(plan.done_steps),
                "failed_steps": len(plan.failed_steps),
                "replan_count": replan_count,
            },
        )

    # ------------------------------------------------------------------
    # 阶段一：Plan
    # ------------------------------------------------------------------

    def _plan(
        self, user_input: str, history: List[Dict[str, Any]], **kwargs: Any
    ) -> Plan:
        """让 LLM 将目标拆解为步骤列表，结果追加到 history。"""
        plan_prompt = (
            f"{user_input}\n\n"
            "请将以上目标拆解为 2~8 个清晰、可执行的子步骤。\n"
            "严格按照以下 JSON 格式输出，不要包含其他内容：\n"
            '{"steps": ["步骤1", "步骤2", ...]}'
        )
        self.context_builder.add_user_message(history, plan_prompt)
        messages = self.context_builder.build_messages(history, **kwargs)
        response = self.think(messages)
        self.context_builder.add_assistant_message(history, response)

        logger.debug("[PlanAndSolve] Plan 原始输出: %s", response.content)
        descs = self._parse_steps(response.content)
        steps = [
            Step(id=i + 1, description=d) for i, d in enumerate(descs[: self.max_steps])
        ]
        return Plan(goal=user_input, steps=steps)

    # ------------------------------------------------------------------
    # 阶段二：Execute（每个步骤在共享 history 上追加，支持工具调用）
    # ------------------------------------------------------------------

    def _execute_step(
        self,
        step: Step,
        plan: Plan,
        history: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        **kwargs: Any,
    ) -> None:
        """执行单个步骤，结果写入 step.result / step.status，并追加到 history。"""
        step.status = StepStatus.RUNNING

        exec_prompt = (
            f"请执行第 {step.id} 步：{step.description}\n\n"
            f"已完成的步骤：\n{plan.completed_context()}"
        )

        self.context_builder.add_user_message(history, exec_prompt)
        last_content = ""

        for attempt in range(self.max_steps_per_task):
            messages = self.context_builder.build_messages(history, **kwargs)
            response = self.think(messages, tools=tools)
            self.context_builder.add_assistant_message(history, response)

            if response.content:
                logger.debug(
                    "[PlanAndSolve] 步骤[%d] attempt%d Thought: %s",
                    step.id,
                    attempt + 1,
                    response.content[:200],
                )
                last_content = response.content

            if not response.has_tool_calls:
                step.status = StepStatus.DONE
                step.result = last_content
                logger.debug(
                    "[PlanAndSolve] 步骤[%d] 完成: %s", step.id, last_content[:100]
                )
                return

            for tc in response.tool_calls:
                logger.debug(
                    "[PlanAndSolve] 步骤[%d] Action: %s(%s)",
                    step.id,
                    tc.name,
                    tc.arguments,
                )
                try:
                    result = self.tool_registry.execute(tc.name, tc.arguments)
                except Exception as e:  # pylint: disable=broad-except
                    result = f"工具调用失败: {e}"
                logger.debug(
                    "[PlanAndSolve] 步骤[%d] Observation: %s",
                    step.id,
                    str(result)[:300],
                )
                self.context_builder.add_tool_result(history, tc.id, tc.name, result)

        step.status = StepStatus.FAILED
        step.error = f"超过最大执行步数 ({self.max_steps_per_task})"
        logger.warning("[PlanAndSolve] 步骤[%d] 失败: %s", step.id, step.error)

    # ------------------------------------------------------------------
    # 阶段三：Replan
    # ------------------------------------------------------------------

    def _replan(
        self,
        plan: Plan,
        failed_step: Step,
        history: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> None:
        """根据失败情况重新规划，替换失败步骤及其后续所有 PENDING 步骤。"""
        failed_info = "\n".join(
            f"[{s.id}] {s.description}：{s.error}" for s in plan.failed_steps
        )
        replan_prompt = (
            f"步骤执行失败：\n{failed_info}\n\n"
            f"已完成的步骤：\n{plan.completed_context()}\n\n"
            "请重新规划剩余需要执行的步骤，严格按照以下 JSON 格式输出：\n"
            '{"steps": ["步骤1", "步骤2", ...]}'
        )
        self.context_builder.add_user_message(history, replan_prompt)
        messages = self.context_builder.build_messages(history, **kwargs)
        response = self.think(messages)
        self.context_builder.add_assistant_message(history, response)

        logger.debug("[PlanAndSolve] Replan 原始输出: %s", response.content)
        new_descs = self._parse_steps(response.content)

        # 保留失败步骤之前的已完成步骤，丢弃失败步骤及其后续
        keep_steps = [
            s
            for s in plan.steps
            if s.id < failed_step.id and s.status == StepStatus.DONE
        ]
        max_id = max((s.id for s in keep_steps), default=0)
        new_steps = [
            Step(id=max_id + i + 1, description=d)
            for i, d in enumerate(new_descs[: self.max_steps])
        ]
        plan.steps = keep_steps + new_steps
        logger.debug(
            "[PlanAndSolve] 重新规划完成，新增 %d 步:\n%s",
            len(new_steps),
            plan.summary(),
        )

    # ------------------------------------------------------------------
    # 阶段四：Synthesize
    # ------------------------------------------------------------------

    def _synthesize(
        self,
        plan: Plan,
        history: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        """汇总所有 DONE 步骤结果，生成最终答案。"""
        steps_summary = "\n\n".join(
            f"步骤 {s.id}：{s.description}\n结果：{s.result or '（无结果）'}"
            for s in plan.steps
            if s.status == StepStatus.DONE
        )
        synthesize_prompt = (
            f"所有步骤已执行完毕，请基于以下执行结果，给出完整的最终答案。\n\n"
            f"原始目标：{plan.goal}\n\n"
            f"各步骤结果：\n{steps_summary}"
        )
        self.context_builder.add_user_message(history, synthesize_prompt)
        messages = self.context_builder.build_messages(history, **kwargs)
        response = self.think(messages)
        self.context_builder.add_assistant_message(history, response)
        return response

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _parse_steps(self, content: str) -> List[str]:
        """从 LLM 输出中解析步骤描述列表，多种格式兼容。"""
        # 尝试提取 JSON 对象中的 steps 字段
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                data = json.loads(json_match.group())
                steps = data.get("steps", [])
                if isinstance(steps, list) and steps:
                    return [str(s) for s in steps]
            except json.JSONDecodeError as e:
                logger.warning("解析步骤列表时出错: %s", e)

        # 尝试提取 JSON 数组
        array_match = re.search(r"\[[\s\S]*\]", content)
        if array_match:
            try:
                steps = json.loads(array_match.group())
                if isinstance(steps, list) and steps:
                    return [str(s) for s in steps]
            except json.JSONDecodeError as e:
                logger.warning("解析步骤列表时出错: %s", e)

        # 降级：按行解析编号列表（1. xxx / - xxx / * xxx）
        lines = [
            re.sub(r"^[\d\.\-\*\s]+", "", line).strip()
            for line in content.splitlines()
            if line.strip() and re.match(r"^[\d\.\-\*]", line.strip())
        ]
        if lines:
            return lines

        # 兜底：整个内容作为单一步骤
        logger.warning("[PlanAndSolve] 无法解析步骤列表，降级为单步执行")
        return [content.strip() or "解决用户问题"]
