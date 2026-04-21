"""
NodeRepository：知识节点数据访问层
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from models.node import (
    NodeSchema,
    NodeBrief,
    NodeContent,
    NodeOrigin,
    NodeRelation,
    MemoryState,
    NodeCreate,
    NodeUpdate,
)
from .base import BaseRepository, _dumps, _loads, new_id, utcnow_str


def _row_to_schema(row: dict) -> NodeSchema:
    """将 SQLite 行字典转为 NodeSchema"""
    return NodeSchema(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        description=row["description"],
        tags=_loads(row["tags"], []),
        content=NodeContent(**(_loads(row["content"], {}))),
        origins=[NodeOrigin(**o) for o in _loads(row["origins"], [])],
        relations=[NodeRelation(**r) for r in _loads(row["relations"], [])],
        memory=MemoryState(
            ease_factor=row["ease_factor"],
            interval=row["interval"],
            repetitions=row["repetitions"],
            due_date=row["due_date"],
            last_review_at=row["last_review_at"],
            mastery_level=row["mastery_level"],
        ),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class NodeRepository(BaseRepository):
    def get_all(self, user_id: str) -> list[NodeBrief]:
        """获取用户所有节点（轻量视图，用于图谱/列表）"""
        rows = self._fetchall(
            "SELECT id, title, description, tags, relations, mastery_level, due_date, "
            "last_review_at, repetitions "
            "FROM nodes WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        )
        return [
            NodeBrief(
                id=r["id"],
                title=r["title"],
                description=r["description"],
                tags=_loads(r["tags"], []),
                relations=[NodeRelation(**x) for x in _loads(r["relations"], [])],
                mastery_level=r["mastery_level"],
                last_review_at=r["last_review_at"],
                repetitions=r["repetitions"] or 0,
                due_date=r["due_date"],
            )
            for r in rows
        ]

    def get_by_id(self, node_id: str) -> Optional[NodeSchema]:
        row = self._fetchone("SELECT * FROM nodes WHERE id = ?", (node_id,))
        return _row_to_schema(row) if row else None

    def get_due_today(self, user_id: str) -> list[NodeBrief]:
        """获取今天到期需要复习的节点"""
        today = datetime.now(timezone.utc).date().isoformat()
        rows = self._fetchall(
            "SELECT id, title, description, tags, relations, mastery_level, due_date, "
            "last_review_at, repetitions "
            "FROM nodes WHERE user_id = ? AND due_date <= ? ORDER BY due_date",
            (user_id, today),
        )
        return [
            NodeBrief(
                id=r["id"],
                title=r["title"],
                description=r["description"],
                tags=_loads(r["tags"], []),
                relations=[NodeRelation(**x) for x in _loads(r["relations"], [])],
                mastery_level=r["mastery_level"],
                due_date=r["due_date"],
                last_review_at=r["last_review_at"],
                repetitions=r["repetitions"] or 0,
            )
            for r in rows
        ]

    def create(self, user_id: str, data: NodeCreate) -> NodeSchema:
        node_id = new_id()
        now = utcnow_str()
        # 初始 due_date = 明天
        due_date = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()

        self._execute(
            """
            INSERT INTO nodes
              (id, user_id, title, description, tags, content, origins, relations,
               ease_factor, interval, repetitions, due_date, last_review_at,
               mastery_level, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                node_id,
                user_id,
                data.title,
                data.description,
                _dumps(data.tags),
                _dumps(data.content.model_dump()),
                _dumps([o.model_dump() for o in data.origins]),
                "[]",
                2.5,
                1,
                0,
                due_date,
                None,
                0.0,
                now,
                now,
            ),
        )
        # 不在这里commit，让调用方控制事务
        return self.get_by_id(node_id)

    def update(self, node_id: str, data: NodeUpdate) -> Optional[NodeSchema]:
        fields, values = [], []
        if data.title is not None:
            fields.append("title = ?")
            values.append(data.title)
        if data.description is not None:
            fields.append("description = ?")
            values.append(data.description)
        if data.tags is not None:
            fields.append("tags = ?")
            values.append(_dumps(data.tags))
        if data.content is not None:
            fields.append("content = ?")
            values.append(_dumps(data.content.model_dump()))
        if data.origins is not None:
            fields.append("origins = ?")
            values.append(_dumps([o.model_dump() for o in data.origins]))
        if data.relations is not None:
            fields.append("relations = ?")
            values.append(_dumps([r.model_dump() for r in data.relations]))

        if not fields:
            return self.get_by_id(node_id)

        fields.append("updated_at = ?")
        values.append(utcnow_str())
        values.append(node_id)
        self._execute(
            f"UPDATE nodes SET {', '.join(fields)} WHERE id = ?", tuple(values)
        )
        # 不在这里commit，让调用方控制事务
        return self.get_by_id(node_id)

    def update_memory(
        self,
        node_id: str,
        ease_factor: float,
        interval: int,
        repetitions: int,
        due_date: str,
        mastery_level: float,
    ) -> None:
        """SM-2 算法更新记忆状态"""
        now = utcnow_str()
        self._execute(
            """
            UPDATE nodes SET
              ease_factor=?, interval=?, repetitions=?,
              due_date=?, last_review_at=?, mastery_level=?, updated_at=?
            WHERE id=?
            """,
            (
                ease_factor,
                interval,
                repetitions,
                due_date,
                now,
                mastery_level,
                now,
                node_id,
            ),
        )
        # 不在这里commit，让调用方控制事务

    def delete(self, node_id: str) -> bool:
        cursor = self._execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        # 不在这里commit，让调用方控制事务
        return cursor.rowcount > 0

    def count(self, user_id: str) -> dict:
        """统计节点数量（总数、已掌握、今日到期）"""
        total = self._fetchone(
            "SELECT COUNT(*) as n FROM nodes WHERE user_id=?", (user_id,)
        )["n"]
        mastered = self._fetchone(
            "SELECT COUNT(*) as n FROM nodes WHERE user_id=? AND mastery_level >= 0.8",
            (user_id,),
        )["n"]
        today = datetime.now(timezone.utc).date().isoformat()
        due = self._fetchone(
            "SELECT COUNT(*) as n FROM nodes WHERE user_id=? AND due_date <= ?",
            (user_id, today),
        )["n"]
        return {"total": total, "mastered": mastered, "due_today": due}
