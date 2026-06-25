"""沉浸式学习画像更新器。

只写统一画像：测验结果转为 user_profile_facts，并刷新 user_profile_overview 的统计快照。
不再维护文件画像，避免画像逻辑分散。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from utils.log_safe import safe_log

logger = logging.getLogger(__name__)


def _accuracy_to_level(accuracy: float) -> str:
    """将正确率映射为掌握等级描述。"""
    if accuracy >= 0.9:
        return "熟练"
    if accuracy >= 0.7:
        return "基本掌握"
    if accuracy >= 0.4:
        return "初步了解"
    return "需要加强"


async def update_profile_from_quiz(
    user_id: str,
    session_id: str,
    chapter_id: int,
    chapter_title: str,
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """根据习题作答结果更新统一用户画像。"""
    if not results:
        return {"status": "ok", "message": "无答题数据"}

    stats = {
        "简单": {"total": 0, "correct": 0},
        "中等": {"total": 0, "correct": 0},
        "困难": {"total": 0, "correct": 0},
    }
    for r in results:
        diff = r.get("difficulty", "中等")
        if diff not in stats:
            diff = "中等"
        stats[diff]["total"] += 1
        if r.get("correct"):
            stats[diff]["correct"] += 1

    total = sum(s["total"] for s in stats.values())
    correct = sum(s["correct"] for s in stats.values())
    overall_accuracy = correct / total if total > 0 else 0
    mastery_level = _accuracy_to_level(overall_accuracy)

    topic = ""
    try:
        from repositories import SessionRepository

        session = SessionRepository().get_by_id(session_id)
        if session:
            topic = (
                (session.topic or session.title or "").replace("[AI课程]", "").strip()
            )
    except Exception:
        logger.exception("读取测验所属会话失败 (session=%s)", safe_log(session_id))

    topic_key = topic or f"session_{session_id}"
    fact_key = f"quiz_mastery:{topic_key}:ch{chapter_id}:{chapter_title}"
    fact_value = (
        f"{topic_key} / {chapter_title} 练习正确率 {overall_accuracy:.0%}，"
        f"掌握评价：{mastery_level}"
    )

    try:
        from repositories import ProfileFactRepository, ProfileOverviewRepository

        fact_repo = ProfileFactRepository()
        fact_repo.upsert_candidate(
            user_id,
            category="ability",
            key=fact_key,
            value=fact_value,
            evidence_type="quiz",
            confidence=max(0.4, min(1.0, overall_accuracy)),
            importance=0.75,
            source_ref="immersive_quiz",
        )
        if overall_accuracy < 0.6:
            fact_repo.upsert_candidate(
                user_id,
                category="mistake_pattern",
                key=f"weak_quiz_area:{topic_key}:ch{chapter_id}:{chapter_title}",
                value=f"{topic_key} / {chapter_title} 练习正确率偏低（{overall_accuracy:.0%}），需要加强",
                evidence_type="quiz",
                confidence=0.8,
                importance=0.85,
                source_ref="immersive_quiz",
            )
        ProfileOverviewRepository().refresh_source_snapshot(user_id)
    except Exception:
        logger.exception("写入统一画像事实失败")

    logger.info(
        "习题画像更新完成: topic=%s, chapter=%s, accuracy=%.0f%%",
        safe_log(topic_key),
        safe_log(chapter_title),
        overall_accuracy * 100,
    )
    return {
        "status": "ok",
        "accuracy": round(overall_accuracy, 2),
        "mastery_level": mastery_level,
        "details": {
            k: {"accuracy": v["correct"] / v["total"] if v["total"] > 0 else 0}
            for k, v in stats.items()
            if v["total"] > 0
        },
    }
