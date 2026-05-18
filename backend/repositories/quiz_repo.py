"""
QuizRepository & StudyLogRepository
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from models.quiz import QuizSchema
from .base import BaseRepository, _loads, _dumps, new_id, utcnow_str


class QuizRepository(BaseRepository):
    def get_by_node(self, node_id: str, limit: int = 20) -> list[QuizSchema]:
        rows = self._fetchall(
            "SELECT * FROM quizzes WHERE node_id=? ORDER BY created_at DESC LIMIT ?",
            (node_id, limit),
        )
        return [self._row_to_schema(r) for r in rows]

    def get_by_id(self, quiz_id: str) -> Optional[QuizSchema]:
        row = self._fetchone("SELECT * FROM quizzes WHERE id=?", (quiz_id,))
        return self._row_to_schema(row) if row else None

    def create(
        self,
        user_id: str,
        node_id: str,
        session_id: Optional[str],
        quiz_type: str,
        question: str,
        options: Optional[list[str]],
        correct_answer: str,
        explanation: str,
    ) -> QuizSchema:
        quiz_id = new_id()
        now = utcnow_str()
        self._execute(
            """
            INSERT INTO quizzes
              (id, user_id, node_id, session_id, quiz_type, question, options,
               correct_answer, explanation, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                quiz_id,
                user_id,
                node_id,
                session_id,
                quiz_type,
                question,
                _dumps(options) if options else None,
                correct_answer,
                explanation,
                now,
            ),
        )
        return self.get_by_id(quiz_id)

    def submit_answer(
        self, quiz_id: str, user_answer: str, is_correct: bool, score: float
    ) -> None:
        now = utcnow_str()
        self._execute(
            """
            UPDATE quizzes SET user_answer=?, is_correct=?, score=?, answered_at=?
            WHERE id=?
            """,
            (user_answer, int(is_correct), score, now, quiz_id),
        )

    @staticmethod
    def _row_to_schema(row: dict) -> QuizSchema:
        return QuizSchema(
            id=row["id"],
            user_id=row["user_id"],
            node_id=row["node_id"],
            session_id=row["session_id"],
            quiz_type=row["quiz_type"],
            question=row["question"],
            options=_loads(row["options"]) if row["options"] else None,
            correct_answer=row["correct_answer"],
            explanation=row["explanation"] or "",
            user_answer=row["user_answer"],
            is_correct=bool(row["is_correct"])
            if row["is_correct"] is not None
            else None,
            score=row["score"],
            answered_at=row["answered_at"],
            created_at=row["created_at"],
        )


class StudyLogRepository(BaseRepository):
    def add_log(
        self, user_id: str, minutes: int, session_id: Optional[str], node_ids: list[str]
    ) -> None:
        """直接插入一条今日学习记录（不合并，用于明确希望保留独立条目的场景，如 AI 课程）。"""
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        self._execute(
            """
            INSERT INTO study_logs (id, user_id, date, minutes, session_id, node_ids, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                new_id(),
                user_id,
                today,
                minutes,
                session_id,
                _dumps(node_ids),
                utcnow_str(),
            ),
        )

    def upsert_today(
        self, user_id: str, minutes: int, session_id: Optional[str], node_ids: list[str]
    ) -> None:
        """更新或插入今日学习记录（每天只保留一条聚合记录）"""
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        existing = self._fetchone(
            "SELECT id, minutes FROM study_logs WHERE user_id=? AND date=?",
            (user_id, today),
        )
        if existing:
            self._execute(
                "UPDATE study_logs SET minutes=minutes+?, node_ids=? WHERE id=?",
                (minutes, _dumps(node_ids), existing["id"]),
            )
        else:
            self._execute(
                """
                INSERT INTO study_logs (id, user_id, date, minutes, session_id, node_ids, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    new_id(),
                    user_id,
                    today,
                    minutes,
                    session_id,
                    _dumps(node_ids),
                    utcnow_str(),
                ),
            )

    def get_recent(self, user_id: str, days: int = 84) -> list[dict]:
        """获取最近 N 天的学习记录（用于热力图），同一天多条记录合并求和"""
        rows = self._fetchall(
            "SELECT date, SUM(minutes) as minutes "
            "FROM study_logs WHERE user_id=? GROUP BY date ORDER BY date DESC LIMIT ?",
            (user_id, days),
        )
        return [{"date": r["date"], "minutes": r["minutes"]} for r in rows]

    def get_streak(self, user_id: str) -> int:
        """计算连续学习天数（同一天多条记录去重）"""
        rows = self._fetchall(
            "SELECT DISTINCT date FROM study_logs WHERE user_id=? ORDER BY date DESC",
            (user_id,),
        )
        if not rows:
            return 0

        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        streak = 0
        prev = None
        for row in rows:
            d = datetime.fromisoformat(row["date"]).date()
            if prev is None:
                # 今天或昨天有记录才开始算连续
                if (today - d).days > 1:
                    break
                prev = d
                streak = 1
            else:
                if (prev - d).days == 1:
                    streak += 1
                    prev = d
                else:
                    break
        return streak
