"""上下文编排层（Context Orchestrator）。

把「用户短期上下文」与「用户画像」从两条平行线，升级为以**当前对话为信号、
按相关性动态召回、token 预算可控**的协同体：

- 短期上下文：近 N 轮原文保留 + 更早内容用「会话滚动摘要」（存 session.workspace）替代，
  组装为 [历史摘要] + [近 N 轮原文]，避免长会话 token 线性膨胀。
- 统一画像激活：根据本轮用户消息推断 task_type，从统一画像总览读取整体判断、知识面、学习行为与策略。
- 统一预算裁剪：各段按字符预算（中文 ≈ 1 char/token）逐段截断，保证 prompt 体积常量级。

设计要点：
- 本模块在 SSE 主路径执行，但**零 LLM 调用**——只做内存计算 + 轻量读库。
- 滚动摘要和画像 consolidate 都挂在 TutorService 的异步链路（不阻塞 SSE）。
- 画像为空时只注入短期上下文，行为自然退化。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── 预算常量（集中调参）────────────────────────────────────────────────
# 近 N 轮对话保留原文（1 轮 ≈ 1 条 user + 1 条 assistant）
RECENT_TURNS = 6
RECENT_MESSAGES = RECENT_TURNS * 2
# 累计消息数超过该阈值才值得生成滚动摘要（避免短会话无谓摘要）
SUMMARIZE_TRIGGER_MESSAGES = RECENT_MESSAGES + 4

# 各段字符预算上限（中文 ≈ 1 char/token）
BUDGET_PROFILE = 1200  # 统一长期画像（整体判断 + 关键事实 + 策略）
BUDGET_HISTORY_SUMMARY = 1500  # 注入对话的短期历史摘要
BUDGET_RECENT_CHARS = 8000  # 近期对话原文字符上限（从尾部保留）
MAX_LEARNING_NODES = 12  # 学习状态快照最多展示的知识点数

DEFAULT_TASK_TYPE = "general"

# ── task_type 关键词规则 ──────────────────────────────────────────────
# 与 ProfileSkillRepository.list_for_task 的 trigger_conditions 对齐。
# 列表有序：靠前的优先匹配（更具体的任务类型放前面）。
_TASK_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "quiz",
        ("测验", "练习", "出题", "做题", "题目", "考考", "测试一下", "刷题", "小测"),
    ),
    (
        "review",
        ("复习", "回顾", "巩固", "记不住", "忘了", "忘记", "温习", "默写"),
    ),
    (
        "path",
        (
            "学习路径",
            "学习计划",
            "怎么学",
            "从哪开始",
            "从哪学",
            "学习路线",
            "规划一下",
            "制定计划",
        ),
    ),
    (
        "explanation",
        (
            "讲解",
            "解释",
            "为什么",
            "怎么",
            "是什么",
            "原理",
            "推导",
            "证明",
            "不懂",
            "不理解",
            "看不懂",
            "举例",
            "举个例子",
            "通俗",
            "详细讲",
        ),
    ),
]


@dataclass
class ContextPack:
    """编排产物：交给 Agent 的对话历史 + 注入 system 的动态文本。"""

    history_messages: (
        list  # [可选摘要 system 消息] + 近 N 轮原文（MessageSchema/dict 混合）
    )
    dynamic_suffix: str  # 注入 system prompt 末尾：统一长期画像
    task_type: str  # 推断出的任务类型（日志/调试用）
    stats: dict = field(default_factory=dict)  # 可观测性指标


class ContextOrchestrator:
    """无状态上下文编排器（可复用单例）。"""

    def __init__(self, *, profile_service: Any = None, node_repo: Any = None) -> None:
        # 延迟导入，避免与 services/repositories 形成导入环。
        # node_repo 参数仅为兼容旧调用方保留；知识面/掌握度已统一进画像服务。
        if profile_service is None:
            from services.profile_service import ProfileMemoryService

            profile_service = ProfileMemoryService()
        self.profile_service = profile_service
        self.node_repo = node_repo

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def assemble(
        self,
        user_id: str,
        session: Any,
        chat_history: list,
        user_message: str,
    ) -> ContextPack:
        """组装上下文包。任何子步骤失败都降级为空，不影响主对话。"""
        task_type = self._infer_task_type(user_message)

        # 1. 短期窗口（近 N 轮原文 + workspace 滚动摘要）
        history_messages, summary_used = self._build_recent_window(
            session, chat_history
        )

        # 2. 统一画像主题感知激活（整体判断 + 知识面 + 学习行为 + 策略）
        profile_text = ""
        try:
            profile_text = (
                self.profile_service.build_activated_profile_text(user_id, task_type)
                or ""
            ).strip()
        except Exception:  # pylint: disable=broad-except
            logger.exception("激活画像文本失败 (user=%s)", user_id)
        profile_text = self._truncate(profile_text, BUDGET_PROFILE)

        # 3. 组装 dynamic_suffix
        dynamic_suffix = self._compose_suffix(profile_text)

        stats = {
            "task_type": task_type,
            "summary_used": summary_used,
            "recent_msgs": len(history_messages) - (1 if summary_used else 0),
            "profile_chars": len(profile_text),
            "suffix_chars": len(dynamic_suffix),
        }
        logger.info(
            "[Orchestrator] task=%s summary=%s recent=%d profile=%dch suffix=%dch",
            stats["task_type"],
            stats["summary_used"],
            stats["recent_msgs"],
            stats["profile_chars"],
            stats["suffix_chars"],
        )
        return ContextPack(
            history_messages=history_messages,
            dynamic_suffix=dynamic_suffix,
            task_type=task_type,
            stats=stats,
        )

    # ------------------------------------------------------------------
    # task_type 推断（轻量关键词规则，零成本可解释）
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_task_type(user_message: str) -> str:
        text = (user_message or "").lower()
        if not text:
            return DEFAULT_TASK_TYPE
        for task_type, keywords in _TASK_RULES:
            for kw in keywords:
                if kw in text:
                    return task_type
        return DEFAULT_TASK_TYPE

    # ------------------------------------------------------------------
    # 短期窗口：近 N 轮原文 + 滚动摘要
    # ------------------------------------------------------------------

    def _build_recent_window(
        self, session: Any, chat_history: list
    ) -> tuple[list, bool]:
        """返回 (history_messages, summary_used)。

        history_messages = [可选摘要 system 消息] + 近期对话原文（从尾部按字符预算保留）。
        - 若 workspace 存在有效滚动摘要：摘要覆盖 [0:summarized_until)，正文取其后的消息。
        - 否则：退化为对全量历史按字符预算保留（接近现状，但有上限）。
        """
        chat_history = list(chat_history or [])
        total = len(chat_history)
        workspace = self._get_workspace(session)
        summary_text = (workspace.get("history_summary") or "").strip()
        try:
            summarized_until = int(workspace.get("summarized_until") or 0)
        except (TypeError, ValueError):
            summarized_until = 0

        summary_used = bool(summary_text) and 0 < summarized_until <= total
        if summary_used:
            body = chat_history[summarized_until:]
        else:
            body = chat_history

        body = self._cap_messages_by_chars(body, BUDGET_RECENT_CHARS)

        history_messages: list = []
        if summary_used and summary_text:
            history_messages.append(
                {
                    "role": "system",
                    "content": "## 既往对话摘要（更早内容已压缩）\n\n"
                    + self._truncate(summary_text, BUDGET_HISTORY_SUMMARY),
                }
            )
        history_messages.extend(body)
        return history_messages, summary_used and bool(summary_text)

    @staticmethod
    def _get_workspace(session: Any) -> dict:
        """从 session 上取嵌套 workspace dict（兼容 SessionSchema / SessionDetail）。"""
        ws = getattr(session, "workspace", None)
        if isinstance(ws, dict):
            return ws
        return {}

    @staticmethod
    def _msg_chars(msg: Any) -> int:
        content = (
            msg.content if hasattr(msg, "content") else (msg or {}).get("content", "")
        )
        return len(content or "")

    @classmethod
    def _cap_messages_by_chars(cls, messages: list, budget: int) -> list:
        """从尾部（最新）开始保留消息，累计字符不超过 budget。至少保留最后一条。"""
        if not messages:
            return []
        kept: list = []
        used = 0
        for msg in reversed(messages):
            c = cls._msg_chars(msg)
            if kept and used + c > budget:
                break
            kept.append(msg)
            used += c
        kept.reverse()
        return kept

    # ------------------------------------------------------------------
    # 学习状态快照
    # ------------------------------------------------------------------

    def _build_learning_state(self, session: Any) -> str:
        node_ids = list(getattr(session, "node_ids_covered", None) or [])
        if not node_ids:
            return ""
        briefs = self.node_repo.list_briefs_by_ids(node_ids[:MAX_LEARNING_NODES])
        if not briefs:
            return ""
        lines: list[str] = []
        for b in briefs:
            level = getattr(b, "mastery_level", 0.0) or 0.0
            tag = self._mastery_tag(level)
            title = getattr(b, "title", "") or ""
            if title:
                lines.append(f"- {title}（掌握度 {level:.2f}，{tag}）")
        return "\n".join(lines)

    @staticmethod
    def _mastery_tag(level: float) -> str:
        if level < 0.34:
            return "薄弱，建议多讲、放慢、补前置"
        if level < 0.67:
            return "进行中，可适度深入"
        return "已掌握，可一笔带过或拔高"

    # ------------------------------------------------------------------
    # 组装 / 预算
    # ------------------------------------------------------------------

    @staticmethod
    def _compose_suffix(profile_text: str) -> str:
        if not profile_text:
            return ""
        return "## 用户画像（统一总览，按当前话题激活）\n\n" + profile_text

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        text = text or ""
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"
