"""
MemoryService：SM-2 间隔重复算法

SM-2 算法简述：
  - quality: 0~5，用户作答质量（5=完全正确，0=完全不记得）
  - easiness factor (EF)：难易因子，初始 2.5
  - interval：下次复习间隔（天）
  - 规则：
    - quality >= 3：记住了
      - repetitions == 0: interval = 1
      - repetitions == 1: interval = 6
      - repetitions >= 2: interval = round(interval * EF)
      EF = EF + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
      EF 最低不低于 1.3
    - quality < 3：重置（interval=1, repetitions=0）
  - mastery_level 随之更新
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from repositories import NodeRepository


def sm2(
    quality: int, ef: float, interval: int, repetitions: int
) -> tuple[float, int, int]:
    """
    运行一步 SM-2，返回 (new_ef, new_interval, new_repetitions)

    quality: 0~5
    """
    if quality >= 3:
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval * ef)
        new_repetitions = repetitions + 1
    else:
        new_interval = 1
        new_repetitions = 0

    new_ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(1.3, new_ef)

    return new_ef, new_interval, new_repetitions


def quality_to_mastery_delta(quality: int) -> float:
    """将 SM-2 quality 转化为掌握度变化量"""
    mapping = {5: 0.15, 4: 0.10, 3: 0.05, 2: -0.05, 1: -0.10, 0: -0.15}
    return mapping.get(quality, 0.0)


class MemoryService:
    def __init__(self, db: sqlite3.Connection):
        self.node_repo = NodeRepository(db)

    def review_node(self, node_id: str, quality: int) -> dict:
        """
        用户复习某节点后调用，返回更新后的记忆状态。
        quality: 0~5
        """
        node = self.node_repo.get_by_id(node_id)
        if not node:
            raise ValueError(f"节点 {node_id} 不存在")

        m = node.memory
        new_ef, new_interval, new_reps = sm2(
            quality, m.ease_factor, m.interval, m.repetitions
        )

        # 计算下次复习日期
        due = (
            (datetime.now(timezone.utc) + timedelta(days=new_interval))
            .date()
            .isoformat()
        )

        # 更新掌握度
        delta = quality_to_mastery_delta(quality)
        new_mastery = max(0.0, min(1.0, m.mastery_level + delta))

        self.node_repo.update_memory(
            node_id=node_id,
            ease_factor=new_ef,
            interval=new_interval,
            repetitions=new_reps,
            due_date=due,
            mastery_level=new_mastery,
        )

        return {
            "node_id": node_id,
            "ease_factor": new_ef,
            "interval": new_interval,
            "repetitions": new_reps,
            "due_date": due,
            "mastery_level": new_mastery,
            "mastery_delta": delta,
        }
