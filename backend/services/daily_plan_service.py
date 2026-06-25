"""
DailyPlanService：每日学习计划生成服务（供 Dashboard 使用）

流程：
1. 检查今天是否已有缓存（daily_plans 表）
2. 若有缓存直接返回
3. 若无缓存：收集用户知识图谱数据 → 调用 LLM → 解析结果 → 写入缓存
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from repositories import NodeRepository, SessionRepository, DailyPlanRepository
from services.llm_factory import get_llm
from utils.log_safe import safe_log

logger = logging.getLogger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────

_PLAN_PROMPT = """你是一个 AI 学习助理，请根据用户的知识图谱数据，生成今日学习计划。

## 用户知识图谱数据

- 总知识节点数：{total_nodes}
- 已掌握节点数（mastery >= 0.8）：{mastered_nodes}
- 今日待复习节点（SM-2 到期）：
{due_nodes_text}
- 掌握度最低的节点（薄弱点）：
{weak_nodes_text}
- 最近 3 次学习会话：{recent_sessions_text}

## 要求

请生成：
1. **今日任务列表**（3~5 条）：优先安排到期复习，再补充薄弱点突破任务。每条任务包含：
   - name：任务名称（简洁，≤20字）
   - tag：学科标签（从节点 tags 中取第一个，无则填"学习"）
   - estimated_minutes：预计时长（分钟，整数）
   - node_id：关联的节点 ID（无关联填 null）
   - type：任务类型，"review"（复习）或 "learn"（新学）

2. **AI 推荐**（一段个性化建议）：
   - focus：今天最应该突破的知识点名称
   - reason：推荐理由（≤60字）
   - minutes：预计总学习时长（分钟）
   - text：完整推荐语（≤100字，自然语言，第二人称）

## 输出格式

只返回 JSON，不要任何其他内容：
{{
  "tasks": [
    {{"name": "...", "tag": "...", "estimated_minutes": 20, "node_id": "...", "type": "review"}},
    ...
  ],
  "recommendation": {{
    "focus": "...",
    "reason": "...",
    "minutes": 45,
    "text": "..."
  }}
}}
"""

# ── Service ───────────────────────────────────────────────────────────────────


class DailyPlanService:
    def __init__(self):
        self.node_repo = NodeRepository()
        self.session_repo = SessionRepository()
        self.plan_repo = DailyPlanRepository()

    async def get_or_generate(self, user_id: str) -> dict:
        """
        获取今日学习计划（有缓存直接返回，否则生成并缓存）。
        返回 { tasks: [...], recommendation: {...} }
        """
        today = datetime.now(timezone.utc).date().isoformat()

        # 1. 查缓存
        cached = self.plan_repo.get_by_date(user_id, today)
        if cached is not None:
            return cached

        # 2. 生成
        try:
            plan = await self._generate(user_id)
        except Exception:  # pylint: disable=broad-except
            logger.exception("DailyPlanService 生成失败，返回空数据")
            plan = {"tasks": [], "recommendation": {}}

        # 3. 写入缓存（空数据不缓存）
        if not plan.get("tasks") and not plan.get("recommendation"):
            return plan
        try:
            self.plan_repo.upsert(user_id, today, plan["tasks"], plan["recommendation"])
        except Exception:  # pylint: disable=broad-except
            logger.exception("DailyPlanService 缓存写入失败")

        return plan

    _MIN_NODES = 1

    async def _generate(self, user_id: str) -> dict:
        all_nodes = self.node_repo.get_all(user_id)
        due_nodes = self.node_repo.get_due_today(user_id)
        weak_nodes = sorted(
            [n for n in all_nodes if n.mastery_level < 0.4],
            key=lambda n: n.mastery_level,
        )[:5]
        recent_sessions = self.session_repo.get_all(user_id, limit=3)

        if len(all_nodes) < self._MIN_NODES:
            logger.info("用户 %s 暂无知识节点，跳过 LLM 生成", safe_log(user_id))
            return {"tasks": [], "recommendation": {}}

        def fmt_node(n):
            tag = n.tags[0] if n.tags else "未分类"
            return (
                f"  - [{n.id}] {n.title}（{tag}，掌握度 {int(n.mastery_level * 100)}%）"
            )

        due_text = "\n".join(fmt_node(n) for n in due_nodes[:8]) or "  （暂无）"
        weak_text = "\n".join(fmt_node(n) for n in weak_nodes) or "  （暂无）"
        sessions_text = (
            "、".join(s.title or "学习会话" for s in recent_sessions) or "暂无"
        )

        total = len(all_nodes)
        mastered = sum(1 for n in all_nodes if n.mastery_level >= 0.8)

        prompt = _PLAN_PROMPT.format(
            total_nodes=total,
            mastered_nodes=mastered,
            due_nodes_text=due_text,
            weak_nodes_text=weak_text,
            recent_sessions_text=sessions_text,
        )

        response = await get_llm(user_id).async_think(
            messages=[
                {"role": "system", "content": "你是学习助理，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ]
        )

        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        return {
            "tasks": data.get("tasks", []),
            "recommendation": data.get("recommendation", {}),
        }
