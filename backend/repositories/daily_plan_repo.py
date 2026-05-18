"""
DailyPlanRepository：每日学习计划的数据访问层
"""

from __future__ import annotations

import json
from typing import Optional

from .base import BaseRepository, new_id, utcnow_str


class DailyPlanRepository(BaseRepository):
    def get_by_date(self, user_id: str, date: str) -> Optional[dict]:
        """读取指定日期的计划；不存在返回 None。返回 {tasks, recommendation}。"""
        row = self._fetchone(
            "SELECT tasks, recommendation FROM daily_plans WHERE user_id=? AND date=?",
            (user_id, date),
        )
        if not row:
            return None
        return {
            "tasks": json.loads(row["tasks"] or "[]"),
            "recommendation": json.loads(row["recommendation"] or "{}"),
        }

    def upsert(
        self, user_id: str, date: str, tasks: list, recommendation: dict
    ) -> None:
        self._execute(
            """
            INSERT OR REPLACE INTO daily_plans
                (id, user_id, date, tasks, recommendation, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                new_id(),
                user_id,
                date,
                json.dumps(tasks, ensure_ascii=False),
                json.dumps(recommendation, ensure_ascii=False),
                utcnow_str(),
            ),
        )
