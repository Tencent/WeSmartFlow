"""
update_mastery：Agent 根据对话判断用户掌握情况，更新节点掌握度
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import sqlite3
from agent_core.tool.base import BaseTool


class UpdateMasteryTool(BaseTool):
    """
    根据用户在对话中的表现更新知识节点掌握度。
    Agent 评估用户对某个概念的理解程度，调用此工具记录。
    """

    name = "update_mastery"
    description = "更新某个知识节点的掌握度，范围 0.0~1.0。当用户展示了对某个概念的理解（或明显误解）时调用。"
    parameters = {
        "type": "object",
        "properties": {
            "node_id": {"type": "string", "description": "知识节点的 id"},
            "delta": {
                "type": "number",
                "description": "掌握度变化量，正数表示提升（如 0.1），负数表示下降（如 -0.1），范围 -0.5~0.5",
            },
            "reason": {
                "type": "string",
                "description": "简短说明为什么调整（供日志记录）",
            },
        },
        "required": ["node_id", "delta"],
    }

    def __init__(self, db: sqlite3.Connection, user_id: str, on_result_hook=None):
        super().__init__(on_result_hook=on_result_hook)
        self._db = db
        self._user_id = user_id

    def run(self, node_id: str, delta: float, reason: str = "") -> str:
        # 查当前掌握度
        row = self._db.execute(
            "SELECT mastery_level FROM nodes WHERE id=? AND user_id=?",
            (node_id, self._user_id),
        ).fetchone()

        if not row:
            return f"Error: 未找到节点 {node_id}"

        current = row["mastery_level"]
        new_level = max(0.0, min(1.0, current + delta))

        self._db.execute(
            "UPDATE nodes SET mastery_level=? WHERE id=?", (new_level, node_id)
        )
        self._db.commit()

        direction = "提升" if delta > 0 else "下降"
        return (
            f"节点 {node_id} 掌握度{direction} {abs(delta):.2f}，"
            f"从 {current:.2f} → {new_level:.2f}。{reason}"
        )
