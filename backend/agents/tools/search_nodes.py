"""
search_nodes：让 Agent 在知识图谱中搜索相关节点
"""

from __future__ import annotations

from agent_core.tool.base import BaseTool
from database import get_db


class SearchNodesTool(BaseTool):
    """
    在用户的知识图谱中搜索与关键词相关的节点。
    Agent 可以用此工具了解用户已有哪些知识、掌握情况如何。
    """

    name = "search_nodes"
    description = "在用户知识图谱中搜索相关知识节点，返回节点标题、描述、掌握程度。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，如概念名称或技术术语",
            },
            "limit": {
                "type": "integer",
                "description": "返回最多几条，默认5",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    def __init__(self, user_id: str):
        super().__init__()
        self._user_id = user_id

    def run(self, query: str = "", limit: int = 5, **kwargs) -> str:
        with get_db() as conn:
            cursor = conn.execute(
                """
                SELECT id, title, description, mastery_level, due_date
                FROM nodes
                WHERE user_id=? AND (title LIKE ? OR description LIKE ?)
                ORDER BY mastery_level ASC
                LIMIT ?
                """,
                (self._user_id, f"%{query}%", f"%{query}%", limit),
            )
            rows = cursor.fetchall()
        if not rows:
            return f"未找到与「{query}」相关的知识节点。"

        result = []
        for r in rows:
            mastery_pct = int(dict(r).get("mastery_level", 0) * 100)
            due = f"（下次复习：{r['due_date']}）" if r["due_date"] else ""
            result.append(
                f"- [{r['id']}] **{r['title']}**：{r['description'][:80]}  "
                f"掌握度 {mastery_pct}%{due}"
            )
        return "\n".join(result)
