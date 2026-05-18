"""
DailyBriefRepository：每日资讯简报的数据访问层
"""

from __future__ import annotations

import json
from typing import Optional

from .base import BaseRepository, new_id, utcnow_str


class DailyBriefRepository(BaseRepository):
    def get_by_date(self, user_id: str, date: str) -> Optional[list]:
        """读取指定日期的简报 groups；不存在返回 None。"""
        row = self._fetchone(
            "SELECT news_groups FROM daily_briefs WHERE user_id=? AND date=?",
            (user_id, date),
        )
        if not row:
            return None
        return json.loads(row["news_groups"] or "[]")

    def upsert(self, user_id: str, date: str, groups: list) -> None:
        """写入或覆盖某日简报。"""
        self._execute(
            """
            INSERT OR REPLACE INTO daily_briefs
                (id, user_id, date, news_groups, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                new_id(),
                user_id,
                date,
                json.dumps(groups, ensure_ascii=False),
                utcnow_str(),
            ),
        )

    def delete_by_date(self, user_id: str, date: str) -> None:
        self._execute(
            "DELETE FROM daily_briefs WHERE user_id=? AND date=?",
            (user_id, date),
        )

    def list_dates_with_data(self, user_id: str) -> list[str]:
        """所有有非空简报的日期，倒序返回。"""
        rows = self._fetchall(
            """
            SELECT date FROM daily_briefs
            WHERE user_id=? AND news_groups != '[]' AND news_groups != ''
            ORDER BY date DESC
            """,
            (user_id,),
        )
        return [r["date"] for r in rows]
