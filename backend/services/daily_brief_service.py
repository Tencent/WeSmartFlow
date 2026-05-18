"""
DailyBriefService：每日资讯简报生成服务（供简报页使用）

流程：
1. 检查今天是否已有缓存（daily_briefs 表）
2. 若有缓存直接返回
3. 若无缓存：读取用户 interests → ReAct Agent 自主搜索 → 输出结构化 JSON → 写入缓存
"""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone

from repositories import UserRepository, DailyBriefRepository
from services.llm_factory import get_llm
from services.quota import check_and_consume
from agent_core.agent.react import ReActAgent
from agent_core.tool.registry import ToolRegistry
from agent_core.context.simple import SimpleContextBuilder
from agent_core.tool.web import TavilySearch, WebFetch, ArxivSearch
from database import get_setting

logger = logging.getLogger(__name__)

# ── System Prompt ─────────────────────────────────────────────────────────────

_BRIEF_SYSTEM_PROMPT = """你是一个 AI 学习资讯助理。你的任务是：根据用户提供的兴趣关键词，通过搜索工具获取真实的最新资讯，然后整理成结构化的每日简报。

## 可用工具

- **tavily_search**：主力搜索工具，返回经过 AI 提炼的高质量结果，优先使用。适合搜索技术资讯、教程、行业动态等。
- **arxiv_search**：专门搜索学术论文，适合关键词偏学术/研究方向时使用（搜索词用英文效果最佳）。
- **web_fetch**：抓取指定 URL 的页面正文，当 tavily_search 返回了有价值的链接但摘要不够详细时，可用此工具获取完整内容。

## 工作流程

1. 对每个兴趣关键词，优先用 tavily_search 搜索最新资讯（搜索词可加"最新"、"教程"、"进展"等修饰词）
2. 若关键词偏学术，额外用 arxiv_search 补充论文资讯（搜索词改为英文）
3. 若某条资讯摘要不够，可用 web_fetch 抓取原文补充细节
4. 所有关键词处理完毕后，输出最终 JSON

## 输出格式

完成搜索后，直接输出以下 JSON（不要包含任何其他文字）：
{
  "groups": [
    {
      "topic": "关键词",
      "icon": "🧩",
      "color": "#6366f1",
      "relevance": 92,
      "items": [
        {
          "title": "资讯标题（≤40字）",
          "summary": "摘要（≤120字，说明核心内容和学习价值）",
          "tags": ["tag1", "tag2"],
          "source": "来源域名（从链接中提取，如 zhihu.com）",
          "relevance": "与用户学习的关联说明（≤60字）",
          "content": "详细内容（≤200字，从搜索结果提炼，没有则填 null）",
          "url": "原文链接（从搜索结果中提取，没有则填 null）"
        }
      ]
    }
  ]
}

## 字段规范
- color 从以下选择：#6366f1 #10b981 #f59e0b #a855f7 #3b82f6 #ef4444 #ec4899
- relevance（分组级）：60~98 之间的整数
- url：使用搜索结果中的真实链接，不要编造
"""

# ── Service ───────────────────────────────────────────────────────────────────


class DailyBriefService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.brief_repo = DailyBriefRepository()

    async def get_or_generate(self, user_id: str) -> dict:
        """
        获取今日资讯简报（有缓存直接返回，否则生成并缓存）。
        返回 { groups: [...], date: 'YYYY-MM-DD', has_data: bool }
        """
        today = datetime.now(timezone.utc).date().isoformat()

        # 1. 查缓存
        groups = self.brief_repo.get_by_date(user_id, today)
        if groups is not None:
            return {"groups": groups, "date": today, "has_data": bool(groups)}

        # 2. 读取用户 interests
        user = self.user_repo.get_by_id(user_id)
        interests = user.preferences.interests if user else []

        if not interests:
            logger.info("用户 %s 未设置兴趣关键词，跳过生成", user_id)
            return {"groups": [], "date": today, "has_data": False}

        # 3. ReAct Agent 搜索 + 整理
        try:
            result = await self._generate(user_id, interests)
        except Exception:  # pylint: disable=broad-except
            logger.exception("DailyBriefService 生成失败，返回空数据")
            result = {"groups": []}

        groups = result.get("groups", [])

        # 4. 写入缓存（空数据不缓存）
        if not groups:
            return {"groups": [], "date": today, "has_data": False}

        try:
            self.brief_repo.upsert(user_id, today, groups)
        except Exception:  # pylint: disable=broad-except
            logger.exception("DailyBriefService 缓存写入失败")

        return {"groups": groups, "date": today, "has_data": True}

    async def regenerate(self, user_id: str) -> dict:
        """强制重新生成今日简报（删除缓存后重新生成）"""
        today = datetime.now(timezone.utc).date().isoformat()
        try:
            self.brief_repo.delete_by_date(user_id, today)
        except Exception:  # pylint: disable=broad-except
            logger.exception("删除简报缓存失败")
        return await self.get_or_generate(user_id)

    async def get_by_date(self, user_id: str, date: str) -> dict:
        """获取指定日期的简报（仅读缓存，不生成）"""
        groups = self.brief_repo.get_by_date(user_id, date)
        if groups is None:
            return {"groups": [], "date": date, "has_data": False}
        return {"groups": groups, "date": date, "has_data": bool(groups)}

    def get_dates_with_data(self, user_id: str) -> list[str]:
        """获取该用户所有有简报数据的日期列表"""
        return self.brief_repo.list_dates_with_data(user_id)

    async def _generate(self, user_id: str, interests: list[str]) -> dict:
        """用 ReAct Agent 自主搜索各关键词，整理成结构化简报 JSON"""
        tavily_key = get_setting(user_id, "tavily_api_key") or os.getenv(
            "TAVILY_API_KEY", ""
        )

        # 构建搜索工具的额度 hook
        def _search_hook():
            check_and_consume(user_id, "search")

        # 构建 ReAct Agent，注册搜索工具（TavilySearch 注入额度 hook）
        registry = ToolRegistry(
            [
                TavilySearch(api_key=tavily_key, before_call_hook=_search_hook),
                WebFetch(),
                ArxivSearch(),
            ]
        )
        agent = ReActAgent(
            llm=get_llm(user_id),
            context_builder=SimpleContextBuilder(_BRIEF_SYSTEM_PROMPT),
            tool_registry=registry,
            max_steps=len(interests) * 3 + 2,  # 每个关键词最多搜3次，留2步余量
        )

        interests_text = "\n".join(f"- {kw}" for kw in interests)
        user_input = f"请为以下兴趣关键词搜索最新资讯并整理成简报：\n{interests_text}"

        result = await agent.async_run(user_input)
        raw = result.output.strip()

        # 提取 JSON
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        # 找到第一个 { 开始解析
        start = raw.find("{")
        if start != -1:
            raw = raw[start:]

        data = json.loads(raw)
        return {"groups": data.get("groups", [])}
