"""统一用户画像服务。

唯一画像链路：
- 长期记忆：user_profile_facts / user_profile_overview / user_profile_skills / user_profile_fact_history。
- 短期记忆：会话滚动摘要和最近对话由 ContextOrchestrator 负责，与本服务输出的长期画像一起注入。
- consolidate 异步执行，不阻塞主对话；主路径只读取已编译好的 overview，保证速度稳定。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from utils.log_safe import safe_log
from models.profile import PROFILE_COMPILE_CONFIDENCE_FLOOR
from repositories import (
    ProfileFactRepository,
    ProfileOverviewRepository,
    ProfileSkillRepository,
)

logger = logging.getLogger(__name__)


def _format_messages_for_prompt(messages: list[dict[str, Any]]) -> str:
    """把 OpenAI messages 压成画像提取用的可读文本。"""
    lines: list[str] = []
    for msg in messages or []:
        role = msg.get("role", "user") if isinstance(msg, dict) else "user"
        content = msg.get("content", "") if isinstance(msg, dict) else ""
        content = str(content or "").strip()
        if not content:
            continue
        speaker = {"user": "用户", "assistant": "助教", "system": "系统"}.get(
            role, role
        )
        lines.append(f"{speaker}：{content}")
    return "\n".join(lines)


def _is_tool_choice_unsupported(content: Any) -> bool:
    text = str(content or "").lower()
    return "tool_choice" in text and (
        "unsupported" in text or "not support" in text or "invalid" in text
    )


def _parse_tool_args(arguments: Any) -> Optional[dict]:
    if isinstance(arguments, dict):
        return arguments
    if not isinstance(arguments, str) or not arguments.strip():
        return None
    try:
        parsed = json.loads(arguments)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        logger.warning("画像工具参数不是合法 JSON: %s", arguments[:200])
        return None


# ---------------------------------------------------------------------------
# LLM Tool 定义
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = [
    "basic",
    "goal",
    "interest",
    "ability",
    "preference",
    "mistake_pattern",
    "habit",
    "interaction",
    "constraints",
]
_VALID_EVIDENCE = ["explicit", "quiz", "behavior", "inference"]

# 阶段1：提取候选 facts
_EXTRACT_FACTS_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_profile_facts",
            "description": (
                "从本轮对话中提取关于用户的、对个性化教学有长期价值的结构化事实。"
                "只提取明确可推断的信息，不要臆造；本轮无新信息时返回空数组。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "facts": {
                        "type": "array",
                        "description": "提取到的用户事实列表（可为空）。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "enum": _VALID_CATEGORIES,
                                    "description": (
                                        "事实分类：basic 基础信息/goal 学习目标/interest 长期兴趣/"
                                        "ability 能力水平/preference 讲解偏好/"
                                        "mistake_pattern 易错薄弱点/habit 学习习惯/"
                                        "interaction 交互风格/constraints 约束条件。"
                                    ),
                                },
                                "key": {
                                    "type": "string",
                                    "description": "该事实的稳定标识键（同类事实复用同一 key，便于增量更新），如 grade/math_level/preferred_explanation。",
                                },
                                "value": {
                                    "type": "string",
                                    "description": "事实内容的简洁描述。",
                                },
                                "evidence_type": {
                                    "type": "string",
                                    "enum": _VALID_EVIDENCE,
                                    "description": (
                                        "证据来源：explicit 用户明确声明/quiz 测验结果/"
                                        "behavior 多次行为体现/inference 单次推断。"
                                    ),
                                },
                                "confidence": {
                                    "type": "number",
                                    "description": "对该事实的置信度 0~1。",
                                },
                                "importance": {
                                    "type": "number",
                                    "description": "该事实对个性化教学的重要度 0~1。",
                                },
                            },
                            "required": ["category", "key", "value", "evidence_type"],
                        },
                    }
                },
                "required": ["facts"],
            },
        },
    }
]
_EXTRACT_TOOL_CHOICE = {
    "type": "function",
    "function": {"name": "save_profile_facts"},
}

# 阶段2：编译 overview + skills
_COMPILE_PROFILE_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "compile_user_profile",
            "description": (
                "根据给定的高可信用户事实和系统统计，编译统一用户画像总览，"
                "以及可按任务激活的教学策略技能。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "overall_judgement": {
                        "type": "string",
                        "description": "对用户的整体判断（100 字以内）：综合目标、兴趣、水平、知识面、学习习惯与互动偏好。",
                    },
                    "interests": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "长期兴趣、偏好主题或常用类比方向；无明确证据则返回空数组。",
                    },
                    "learning_level": {
                        "type": "string",
                        "description": "用户当前能力水平概述，需结合事实与掌握度统计。",
                    },
                    "knowledge_scope": {
                        "type": "string",
                        "description": "用户已涉及的知识面与掌握分布，需结合知识图谱统计。",
                    },
                    "dialogue_preference": {
                        "type": "string",
                        "description": "用户偏好的对话/讲解方式，如是否需要步骤拆解、类比、追问、简洁回答等。",
                    },
                    "learning_behavior": {
                        "type": "string",
                        "description": "学习时长、活跃度、会话习惯等行为判断，需结合系统统计。",
                    },
                    "weakness_summary": {
                        "type": "string",
                        "description": "用户的薄弱点/易错点概述。",
                    },
                    "strategy_summary": {
                        "type": "string",
                        "description": "面向助教的整体辅导策略，要求简短、可执行。",
                    },
                    "skills": {
                        "type": "array",
                        "description": "可按任务激活的教学策略技能（可为空）。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "skill_name": {
                                    "type": "string",
                                    "description": "技能标识，如 explanation_style/learning_path/quiz_generation/review_schedule/interaction_style。",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "该策略的具体内容/指引。",
                                },
                                "trigger_conditions": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "可激活该技能的 task_type 列表，为空表示通用。",
                                },
                                "priority": {
                                    "type": "number",
                                    "description": "优先级 0~1。",
                                },
                            },
                            "required": ["skill_name", "content"],
                        },
                    },
                },
                "required": ["overall_judgement"],
            },
        },
    }
]
_COMPILE_TOOL_CHOICE = {
    "type": "function",
    "function": {"name": "compile_user_profile"},
}


class ProfileMemoryService:
    """结构化画像记忆服务。"""

    def __init__(self) -> None:
        self.fact_repo = ProfileFactRepository()
        self.overview_repo = ProfileOverviewRepository()
        self.skill_repo = ProfileSkillRepository()

    # ------------------------------------------------------------------
    # 对外：注入用画像文本
    # ------------------------------------------------------------------

    def build_profile_text(self, user_id: str) -> str:
        """读取统一画像总览，拼成可注入 system prompt 的文本。"""
        return self.build_activated_profile_text(user_id, "general")

    def build_activated_profile_text(
        self, user_id: str, task_type: str = "general"
    ) -> str:
        """从统一画像总览读取画像，并按当前 task_type 激活教学策略。"""
        parts: list[str] = []

        try:
            row = self.overview_repo.get(user_id)
        except Exception:  # pylint: disable=broad-except
            logger.exception("读取统一画像失败 (user=%s)", safe_log(user_id))
            row = None

        if row:
            if row.get("overall_judgement"):
                parts.append(row["overall_judgement"].strip())
            detail_lines: list[str] = []
            interests = row.get("interests") or []
            if interests:
                detail_lines.append(
                    "**兴趣**：" + "、".join(str(x) for x in interests[:6])
                )
            field_map = [
                ("learning_level", "能力水平"),
                ("knowledge_scope", "知识面"),
                ("weakness_summary", "薄弱点"),
                ("dialogue_preference", "对话偏好"),
                ("learning_behavior", "学习行为"),
                ("strategy_summary", "整体策略"),
            ]
            for key, label in field_map:
                value = (row.get(key) or "").strip()
                if value:
                    detail_lines.append(f"**{label}**：{value}")
            fact_lines = self._format_facts_snapshot(row.get("facts_snapshot") or [])
            if fact_lines:
                detail_lines.append("**关键长期事实**：\n" + fact_lines)
            if not row.get("knowledge_scope") and not row.get("learning_behavior"):
                snapshot_hint = self._format_source_snapshot(
                    row.get("source_snapshot") or {}
                )
                if snapshot_hint:
                    detail_lines.append("**系统统计**：\n" + snapshot_hint)
            if detail_lines:
                parts.append("\n".join(detail_lines))

        try:
            skills = self.skill_repo.list_for_task(user_id, task_type)
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "读取激活技能失败 (user=%s, task=%s)",
                safe_log(user_id),
                safe_log(task_type),
            )
            skills = []
        if skills:
            lines: list[str] = []
            for s in skills[:6]:
                name = (s.get("skill_name") or "").strip()
                content = (s.get("content") or "").strip()
                if content:
                    prefix = f"[{name}] " if name else ""
                    lines.append(f"- {prefix}{content}")
            if lines:
                parts.append("**教学策略（已按当前任务激活）**：\n" + "\n".join(lines))

        return "\n\n".join(p for p in parts if p)

    # ------------------------------------------------------------------
    # consolidate 主流程
    # ------------------------------------------------------------------

    async def consolidate_from_messages(
        self, user_id: str, messages: list[dict[str, Any]], llm_caller: Any
    ) -> bool:
        """从对话消息 consolidate 结构化画像。失败静默返回 False。"""
        if not messages:
            return True
        try:
            # 0. 时间衰减惰性归档
            archived = self.fact_repo.decay_maintenance(user_id)

            # 1. 提取候选 facts
            candidates = await self._extract_facts(messages, llm_caller)
            if candidates is None:
                logger.warning("画像提取失败，跳过本轮 (user=%s)", safe_log(user_id))
                return False

            # 2. 按优先级落库
            stats = {"created": 0, "reinforced": 0, "superseded": 0, "ignored": 0}
            for c in candidates:
                outcome = self._persist_candidate(user_id, c)
                if outcome in stats:
                    stats[outcome] += 1

            # 3. 汇总画像事实 + 知识图谱/学习行为快照，编译统一画像总览
            facts = self.fact_repo.list_active(
                user_id, min_effective_confidence=PROFILE_COMPILE_CONFIDENCE_FLOOR
            )
            source_snapshot = self.overview_repo.build_source_snapshot(user_id)
            compiled = False
            if facts:
                compiled = await self._compile_overview(
                    user_id, facts, source_snapshot, llm_caller
                )
            else:
                self.overview_repo.refresh_source_snapshot(user_id)

            logger.info(
                "画像 consolidate 完成 (user=%s) 归档=%d 提取=%d 落库=%s 编译=%s",
                safe_log(user_id),
                archived,
                len(candidates),
                stats,
                compiled,
            )
            return True
        except Exception:  # pylint: disable=broad-except
            logger.exception("画像 consolidate 异常 (user=%s)", safe_log(user_id))
            return False

    # ------------------------------------------------------------------
    # 阶段1：提取
    # ------------------------------------------------------------------

    async def _extract_facts(
        self, messages: list[dict[str, Any]], llm_caller: Any
    ) -> Optional[list[dict]]:
        """forced tool_call 提取候选 facts；返回候选列表或 None（失败）。"""
        conversation = _format_messages_for_prompt(messages)
        chat_messages = [
            {
                "role": "system",
                "content": (
                    "你是用户画像提取助手。从对话中识别对个性化教学有长期价值的用户特征，"
                    "调用 save_profile_facts 工具以结构化数组返回。"
                    "只提取明确、可靠的信息，宁缺毋滥；无新信息时返回空数组。"
                ),
            },
            {"role": "user", "content": f"## 本轮对话\n{conversation}"},
        ]
        args = await self._call_tool(
            llm_caller, chat_messages, _EXTRACT_FACTS_TOOL, _EXTRACT_TOOL_CHOICE
        )
        if args is None:
            return None
        facts = args.get("facts")
        if not isinstance(facts, list):
            return []
        return [
            f for f in facts if isinstance(f, dict) and f.get("key") and f.get("value")
        ]

    def _persist_candidate(self, user_id: str, c: dict) -> str:
        category = c.get("category", "")
        if category not in _VALID_CATEGORIES:
            return "ignored"
        evidence_type = c.get("evidence_type", "inference")
        if evidence_type not in _VALID_EVIDENCE:
            evidence_type = "inference"
        return self.fact_repo.upsert_candidate(
            user_id,
            category=category,
            key=str(c["key"]).strip(),
            value=str(c["value"]).strip(),
            evidence_type=evidence_type,
            confidence=float(c.get("confidence", 0.5) or 0.5),
            importance=float(c.get("importance", 0.5) or 0.5),
            source_ref="consolidate",
        )

    # ------------------------------------------------------------------
    # 阶段2：编译
    # ------------------------------------------------------------------

    async def _compile_overview(
        self,
        user_id: str,
        facts: list[dict],
        source_snapshot: dict[str, Any],
        llm_caller: Any,
    ) -> bool:
        facts_text = self._format_facts(facts)
        source_text = self._format_source_snapshot(source_snapshot)
        chat_messages = [
            {
                "role": "system",
                "content": (
                    "你是用户画像编译助手。基于高可信画像事实和系统统计快照，"
                    "调用 compile_user_profile 工具生成统一画像总览与教学策略技能。"
                    "必须只使用输入中有证据的信息；无法判断的字段写空字符串或空数组。"
                    "输出必须是自然中文，禁止混入代码注释、英文解释或推理过程。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## 高可信用户事实\n{facts_text or '（暂无）'}\n\n"
                    f"## 系统统计快照\n{source_text or '（暂无）'}"
                ),
            },
        ]
        args = await self._call_tool(
            llm_caller, chat_messages, _COMPILE_PROFILE_TOOL, _COMPILE_TOOL_CHOICE
        )
        if args is None:
            return False

        overall_judgement = str(args.get("overall_judgement", "")).strip()
        dialogue_preference = str(args.get("dialogue_preference", "")).strip()
        learning_level = str(args.get("learning_level", "")).strip()
        weakness = str(args.get("weakness_summary", "")).strip()
        interests = args.get("interests")
        if not isinstance(interests, list):
            interests = []

        facts_snapshot = [
            {
                "id": f.get("id"),
                "category": f.get("category"),
                "key": f.get("key"),
                "value": f.get("value"),
                "evidence_type": f.get("evidence_type"),
                "effective_confidence": f.get("effective_confidence"),
                "importance": f.get("importance"),
            }
            for f in facts
        ]
        self.overview_repo.upsert(
            user_id,
            overall_judgement=overall_judgement,
            interests=[str(x).strip() for x in interests if str(x).strip()],
            learning_level=learning_level,
            knowledge_scope=str(args.get("knowledge_scope", "")).strip(),
            dialogue_preference=dialogue_preference,
            learning_behavior=str(args.get("learning_behavior", "")).strip(),
            weakness_summary=weakness,
            strategy_summary=str(args.get("strategy_summary", "")).strip(),
            source_snapshot=source_snapshot,
            facts_snapshot=facts_snapshot,
        )

        fact_ids = [f["id"] for f in facts]
        skills = args.get("skills")
        if isinstance(skills, list):
            for s in skills:
                if (
                    not isinstance(s, dict)
                    or not s.get("skill_name")
                    or not s.get("content")
                ):
                    continue
                triggers = s.get("trigger_conditions")
                self.skill_repo.upsert(
                    user_id,
                    skill_name=str(s["skill_name"]).strip(),
                    content=str(s["content"]).strip(),
                    trigger_conditions=triggers if isinstance(triggers, list) else [],
                    source_fact_ids=fact_ids,
                    priority=float(s.get("priority", 0.5) or 0.5),
                )
        return True

    @staticmethod
    def _format_facts_snapshot(facts: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        label_map = {
            "basic": "基础",
            "goal": "目标",
            "interest": "兴趣",
            "ability": "能力",
            "preference": "偏好",
            "mistake_pattern": "薄弱/易错",
            "habit": "习惯",
            "interaction": "互动",
            "constraints": "约束",
        }
        for fact in facts[:8]:
            value = str(fact.get("value") or "").strip()
            if not value:
                continue
            category = label_map.get(str(fact.get("category") or ""), "事实")
            lines.append(f"- [{category}] {value}")
        return "\n".join(lines)

    @staticmethod
    def _format_source_snapshot(snapshot: dict[str, Any]) -> str:
        knowledge = snapshot.get("knowledge") or {}
        behavior = snapshot.get("learning_behavior") or {}
        lines = [
            (
                "- 知识点：共 {total} 个，已掌握 {mastered} 个，薄弱 {weak} 个，"
                "平均掌握度 {avg:.2f}"
            ).format(
                total=knowledge.get("total_nodes", 0),
                mastered=knowledge.get("mastered_nodes", 0),
                weak=knowledge.get("weak_nodes", 0),
                avg=float(knowledge.get("average_mastery") or 0.0),
            ),
            (
                "- 学习行为：共 {sessions} 次会话，完成 {completed} 次，累计 {minutes} 分钟，"
                "活跃 {days} 天，活跃日均 {avg_day} 分钟"
            ).format(
                sessions=behavior.get("total_sessions", 0),
                completed=behavior.get("completed_sessions", 0),
                minutes=behavior.get("total_minutes", 0),
                days=behavior.get("active_days", 0),
                avg_day=behavior.get("average_minutes_per_active_day", 0),
            ),
        ]
        if knowledge.get("top_tags"):
            lines.append("- 高频领域：" + "、".join(knowledge["top_tags"]))
        if behavior.get("recent_topics"):
            lines.append("- 最近主题：" + "、".join(behavior["recent_topics"]))
        weak_nodes = knowledge.get("recent_weak_nodes") or []
        if weak_nodes:
            lines.append(
                "- 近期薄弱知识点："
                + "、".join(
                    f"{x.get('title', '')}({float(x.get('mastery_level') or 0):.2f})"
                    for x in weak_nodes
                    if x.get("title")
                )
            )
        strong_nodes = knowledge.get("recent_strong_nodes") or []
        if strong_nodes:
            lines.append(
                "- 近期掌握较好知识点："
                + "、".join(
                    f"{x.get('title', '')}({float(x.get('mastery_level') or 0):.2f})"
                    for x in strong_nodes
                    if x.get("title")
                )
            )
        return "\n".join(line for line in lines if line.strip())

    @staticmethod
    def _format_facts(facts: list[dict]) -> str:
        lines = []
        for f in facts:
            eff = f.get("effective_confidence", f.get("confidence", 0))
            lines.append(
                f"- [{f['category']}/{f['key']}] {f['value']} "
                f"(证据={f['evidence_type']}, 有效置信度={eff:.2f}, 重要度={f.get('importance', 0.5):.2f})"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LLM 调用（forced→auto 降级）
    # ------------------------------------------------------------------

    @staticmethod
    async def _call_tool(
        llm_caller: Any,
        chat_messages: list[dict],
        tools: list[dict],
        tool_choice: dict,
    ) -> Optional[dict]:
        """调用 LLM 强制 tool_call，返回解析后的 args dict 或 None。"""
        try:
            response = await llm_caller.async_think(
                messages=chat_messages, tools=tools, tool_choice=tool_choice
            )
            if response.is_error and _is_tool_choice_unsupported(response.content):
                logger.warning("forced tool_choice 不支持，降级 auto 重试")
                response = await llm_caller.async_think(
                    messages=chat_messages, tools=tools, tool_choice="auto"
                )
            if not response.has_tool_calls:
                logger.warning(
                    "画像 LLM 未调用工具 (finish_reason=%s)", response.finish_reason
                )
                return None
            return _parse_tool_args(response.tool_calls[0].arguments)
        except Exception:  # pylint: disable=broad-except
            logger.exception("画像 LLM 调用异常")
            return None
