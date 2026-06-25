"""
API 额度管理服务

双轨逻辑：
- 用户自己配置了 API Key（settings 表中非空）→ 不限次数
- 使用平台公共 Key（环境变量 fallback）→ 每用户有免费总额度限制（用完即止）

类别：
- llm: LLM 对话/生成
- search: Tavily 搜索
- image: 图像生成
"""

from __future__ import annotations

import logging

from database import get_setting, get_db
from config import FREE_LLM_TOTAL, FREE_SEARCH_TOTAL, FREE_IMAGE_TOTAL
from utils.log_safe import safe_log

logger = logging.getLogger(__name__)

# 各类别的免费总额度
_TOTAL_LIMITS = {
    "llm": FREE_LLM_TOTAL,
    "search": FREE_SEARCH_TOTAL,
    "image": FREE_IMAGE_TOTAL,
}


class QuotaExceededError(Exception):
    """免费额度已用完"""

    def __init__(self, category: str, limit: int):
        self.category = category
        self.limit = limit
        super().__init__(
            f"免费{_CATEGORY_NAMES.get(category, category)}额度已用完"
            f"（总共{limit}次）。请在设置页面配置您自己的 API Key 以解除限制。"
        )


_CATEGORY_NAMES = {
    "llm": "对话",
    "search": "搜索",
    "image": "图像生成",
}


def is_using_platform_key(user_id: str, category: str) -> bool:
    """
    判断用户是否在使用平台公共 Key（即用户自己的 settings 为空）。
    category: 'llm' | 'search' | 'image'
    """

    if category == "llm":
        user_key = get_setting(user_id, "llm_api_key")
    elif category == "search":
        user_key = get_setting(user_id, "tavily_api_key")
    elif category == "image":
        user_key = get_setting(user_id, "img_api_key")
    else:
        return False

    # 用户 settings 为空或 None → 使用平台公共 Key
    return not user_key


def get_usage(user_id: str) -> dict:
    """
    获取用户各类别的累计使用量和总额度。
    返回: {
        "llm": {"used": 5, "limit": 100, "is_platform": True},
        "search": {"used": 2, "limit": 30, "is_platform": True},
        "image": {"used": 0, "limit": 15, "is_platform": False},
    }
    """
    with get_db() as conn:
        rows = conn.execute(
            "SELECT category, count FROM api_usage WHERE user_id=?",
            (user_id,),
        ).fetchall()
        usage_map = {row["category"]: row["count"] for row in rows}

    result = {}
    for cat, limit in _TOTAL_LIMITS.items():
        is_platform = is_using_platform_key(user_id, cat)
        result[cat] = {
            "used": usage_map.get(cat, 0),
            "limit": limit if is_platform else -1,  # -1 表示无限制
            "is_platform": is_platform,
        }
    return result


def check_and_consume(user_id: str, category: str) -> None:
    """
    检查额度并消费一次。如果超限则抛出 QuotaExceededError。
    如果用户使用自己的 Key，直接通过不计数。

    Args:
        user_id: 用户 ID
        category: 'llm' | 'search' | 'image'
    """
    # 用户使用自己的 Key → 不限制
    if not is_using_platform_key(user_id, category):
        return

    limit = _TOTAL_LIMITS.get(category, 0)
    if limit <= 0:
        # 未配置额度限制，直接通过
        return

    with get_db() as conn:
        # 原子操作：仅当 count < limit 时才 +1，避免 TOCTOU 竞态
        conn.execute(
            """
            INSERT INTO api_usage (user_id, category, count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, category)
            DO UPDATE SET count = count + 1
            WHERE count < ?
            """,
            (user_id, category, limit),
        )

        # 检查是否真的写入成功（changes == 0 说明已达上限）
        changes = conn.execute("SELECT changes()").fetchone()[0]
        if changes == 0:
            raise QuotaExceededError(category, limit)

        # 读取最新计数用于日志
        row = conn.execute(
            "SELECT count FROM api_usage WHERE user_id=? AND category=?",
            (user_id, category),
        ).fetchone()
        current_count = row["count"] if row else 0
        logger.debug(
            "用户 %s 消费 %s 额度: %d/%d",
            safe_log(user_id),
            category,
            current_count,
            limit,
        )
