"""Reflection Agent 实现。

范式：Generate → Reflect → Refine（循环）

1. Generate: LLM 生成初始答案，内部支持工具调用（ReAct 小循环）
2. Reflect:  独立 critic 调用，返回结构化审查意见
             {"pass": bool, "issues": [...], "suggestions": [...]}
3. Refine:   基于结构化意见改进答案，内部同样支持工具调用
4. 重复 Reflect → Refine，直到 pass=True 或达到 max_reflections

所有阶段统一通过 context_builder + history 管理消息：
- Generate / Refine 阶段共用同一 history（保留完整对话上下文）
- Reflect 阶段使用独立 history（critic 角色独立，不污染主对话）
- 每轮反思结果写入 AgentResult.metadata["reflection_history"]
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from ..context.base import BaseContextBuilder
from ..context.simple import SimpleContextBuilder
from ..llm.base import BaseLLM, LLMResponse
from ..tool.registry import ToolRegistry
from .base import AgentResult, BaseAgent
from .events import AgentFinishReason

logger = logging.getLogger(__name__)

# ── 默认 system prompt ────────────────────────────────────────────────────────

_DEFAULT_SYSTEM_PROMPT = """你是一个严谨、全面的智能助手。

请认真分析用户的问题，给出详细、准确的回答。
如有必要，可以调用工具获取信息，再综合给出答案。"""

_DEFAULT_REFLECT_SYSTEM_PROMPT = """你是一个严格的批评者，负责审查答案的质量。

请对给定的答案进行批判性评估，严格按照以下 JSON 格式输出，不要包含其他内容：
{
  "pass": true/false,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"]
}

评估维度：
1. 事实准确性：是否有错误或不准确之处
2. 逻辑严密性：推理是否有漏洞
3. 完整性：是否遗漏重要信息或角度
4. 表达清晰度：结构是否清晰，表达是否准确

如果答案质量足够好，将 "pass" 设为 true，issues 和 suggestions 可为空列表。
否则将 "pass" 设为 false，并给出具体的问题和改进建议。"""

_REFINE_PROMPT = """请根据以下审查意见，改进你的答案：

发现的问题：
{issues}

改进建议：
{suggestions}

请给出改进后的完整答案。"""


class ReflectionAgent(BaseAgent):
    """Reflection 范式 Agent。

    执行流程::

        1. generate: LLM 生成初始答案（可调用工具）
        2. reflect:  独立 critic 调用，返回结构化审查意见
                     {"pass": bool, "issues": [...], "suggestions": [...]}
        3. refine:   基于结构化意见改进答案（可调用工具）
        4. 重复 reflect → refine，直到 pass=True 或达到 max_reflections

    ``context_builder`` 控制 generate/refine 阶段的 system prompt，
    ``reflection_context_builder`` 控制 reflect 阶段的 system prompt，
    两者均可选，不传时使用内置默认 prompt。
    """

    def __init__(
        self,
        llm: BaseLLM,
        context_builder: Optional[BaseContextBuilder] = None,
        tool_registry: Optional[ToolRegistry] = None,
        max_steps: int = 5,
        max_reflections: int = 3,
        reflection_context_builder: Optional[BaseContextBuilder] = None,
        llm_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            llm:                        LLM 实例。
            context_builder:            生成/改进阶段的上下文构建器，为 None 时使用内置默认。
            tool_registry:              工具注册表。
            max_steps:                  generate/refine 阶段工具调用最大轮次。
            max_reflections:            最大反思轮次（reflect → refine 循环次数）。
            reflection_context_builder: 反思阶段的上下文构建器，为 None 时使用内置批评者 prompt。
            llm_config:                 透传给 LLM 的额外参数。
        """
        super().__init__(
            llm=llm,
            context_builder=context_builder
            or SimpleContextBuilder(_DEFAULT_SYSTEM_PROMPT),
            tool_registry=tool_registry,
            max_steps=max_steps,
            llm_config=llm_config,
        )
        self.max_reflections = max_reflections
        self.reflection_context_builder = (
            reflection_context_builder
            or SimpleContextBuilder(_DEFAULT_REFLECT_SYSTEM_PROMPT)
        )

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def _run(self, user_input: str, **kwargs: Any) -> AgentResult:
        history: List[Dict[str, Any]] = []
        tools = self.tool_registry.get_definitions() or None
        reflection_history: List[Dict[str, Any]] = []
        reflect_history: List[Dict[str, Any]] = []  # critic 跨轮保留

        # ── 阶段一：Generate ──────────────────────────────────────────
        logger.debug("[Reflection] ── Generate ──")
        current_answer = self._generate(user_input, history, tools, **kwargs)
        logger.debug("[Reflection] 初始答案: %s", current_answer[:200])

        # ── 阶段二/三：Reflect → Refine 循环 ─────────────────────────
        for round_idx in range(1, self.max_reflections + 1):
            logger.debug("[Reflection] ── Reflect 第 %d 轮 ──", round_idx)
            critique = self._reflect(
                user_input, current_answer, reflect_history, **kwargs
            )
            logger.debug(
                "[Reflection] 审查结果: pass=%s, issues=%d 条",
                critique.get("pass"),
                len(critique.get("issues", [])),
            )

            # 记录本轮反思历史
            reflection_history.append({"round": round_idx, "reflection": critique})

            if critique.get("pass", False):
                logger.debug("[Reflection] Critic 满意，共反思 %d 轮，结束", round_idx)
                break

            issues = critique.get("issues", [])
            suggestions = critique.get("suggestions", [])
            logger.debug(
                "[Reflection] ── Refine 第 %d 轮（%d 个问题）──", round_idx, len(issues)
            )
            current_answer = self._refine(
                issues=issues,
                suggestions=suggestions,
                history=history,
                tools=tools,
                **kwargs,
            )
            logger.debug("[Reflection] 改进后答案: %s", current_answer[:200])

        final_response = LLMResponse(content=current_answer)

        return AgentResult(
            finish_reason=AgentFinishReason.STOP,
            final_response=final_response,
            history=history,
            metadata={
                "reflection_history": reflection_history,
                "total_rounds": len(reflection_history),
            },
        )

    # ------------------------------------------------------------------
    # 阶段一：Generate（支持工具调用的 ReAct 小循环）
    # ------------------------------------------------------------------

    def _generate(
        self,
        user_input: str,
        history: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        **kwargs: Any,
    ) -> str:
        """生成初始答案，内部支持工具调用。结果追加到 history。"""
        self.context_builder.add_user_message(history, user_input)
        last_content = ""

        for step in range(self.max_steps):
            messages = self.context_builder.build_messages(history, **kwargs)
            response = self.think(messages, tools=tools)
            self.context_builder.add_assistant_message(history, response)

            if response.content:
                logger.debug(
                    "[Reflection] Generate step%d Thought: %s",
                    step + 1,
                    response.content[:200],
                )
                last_content = response.content

            if not response.has_tool_calls:
                return last_content

            for tc in response.tool_calls:
                logger.debug("[Reflection] Action: %s(%s)", tc.name, tc.arguments)
                try:
                    result = self.tool_registry.execute(tc.name, tc.arguments)
                except Exception as e:  # pylint: disable=broad-except
                    result = f"工具调用失败: {e}"
                logger.debug("[Reflection] Observation: %s", str(result)[:300])
                self.context_builder.add_tool_result(history, tc.id, tc.name, result)

        return last_content

    # ------------------------------------------------------------------
    # 阶段二：Reflect（独立 critic 调用，不共享主 history）
    # ------------------------------------------------------------------

    def _reflect(
        self,
        user_input: str,
        current_answer: str,
        reflect_history: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """对当前答案进行批判性审查，返回结构化意见。

        reflect_history 跨轮保留，让 critic 能看到上轮自己提出的问题，
        从而判断改进是否真正解决了上轮的问题。

        Returns:
            {"pass": bool, "issues": [...], "suggestions": [...]}
        """
        prompt = f"用户问题：{user_input}\n\n待审查的答案：\n{current_answer}"

        messages = self.reflection_context_builder.build_messages(
            reflect_history, current_message=prompt
        )
        response = self.think(messages, tool_choice="none")
        logger.debug("[Reflection] Critic 原始输出: %s", response.content)

        # 将本轮对话追加到 reflect_history，下轮可以看到
        self.reflection_context_builder.add_user_message(reflect_history, prompt)
        self.reflection_context_builder.add_assistant_message(reflect_history, response)

        return self._parse_critique(response.content)

    # ------------------------------------------------------------------
    # 阶段三：Refine（基于结构化意见改进，支持工具调用）
    # ------------------------------------------------------------------

    def _refine(
        self,
        issues: List[str],
        suggestions: List[str],
        history: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        **kwargs: Any,
    ) -> str:
        """基于结构化审查意见改进答案，结果追加到 history。"""
        issues_text = (
            "\n".join(f"- {i}" for i in issues) if issues else "（无具体问题）"
        )
        suggestions_text = (
            "\n".join(f"- {s}" for s in suggestions)
            if suggestions
            else "（无具体建议）"
        )
        prompt = _REFINE_PROMPT.format(issues=issues_text, suggestions=suggestions_text)

        self.context_builder.add_user_message(history, prompt)
        last_content = ""

        for step in range(self.max_steps):
            messages = self.context_builder.build_messages(history, **kwargs)
            response = self.think(messages, tools=tools)
            self.context_builder.add_assistant_message(history, response)

            if response.content:
                logger.debug(
                    "[Reflection] Refine step%d: %s", step + 1, response.content[:200]
                )
                last_content = response.content

            if not response.has_tool_calls:
                return last_content

            for tc in response.tool_calls:
                logger.debug(
                    "[Reflection] Refine Action: %s(%s)", tc.name, tc.arguments
                )
                try:
                    result = self.tool_registry.execute(tc.name, tc.arguments)
                except Exception as e:  # pylint: disable=broad-except
                    result = f"工具调用失败: {e}"
                logger.debug("[Reflection] Refine Observation: %s", str(result)[:300])
                self.context_builder.add_tool_result(history, tc.id, tc.name, result)

        return last_content

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _parse_critique(self, content: str) -> Dict[str, Any]:
        """从 LLM 输出中解析结构化审查意见，多种格式兼容。"""
        # 尝试提取 JSON 对象
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return {
                    "pass": bool(data.get("pass", False)),
                    "issues": list(data.get("issues", [])),
                    "suggestions": list(data.get("suggestions", [])),
                }
            except json.JSONDecodeError:
                pass

        # 降级：文本中包含明确通过信号则视为通过
        pass_signals = [
            "pass: true",
            'pass":true',
            "质量足够",
            "无需修改",
            "答案正确",
            "lgtm",
        ]
        if any(sig in content.lower() for sig in pass_signals):
            return {"pass": True, "issues": [], "suggestions": []}

        # 兜底：整个内容作为一条建议，要求改进
        logger.warning("[Reflection] 无法解析结构化审查意见，降级处理")
        return {
            "pass": False,
            "issues": ["答案需要改进"],
            "suggestions": [content.strip()],
        }
