"""
update_node：Agent 已整理好新内容后，更新知识图谱中某个节点的信息
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import sqlite3
from agent_core.tool.base import BaseTool
from models.node import NodeContent, NodeUpdate
from repositories.node_repo import NodeRepository


class UpdateNodeTool(BaseTool):
    """
    将 Agent 整理好的新内容更新到已有知识节点中。
    可用于：对话中发现节点描述不准确、补充要点、追加示例、纠正常见误区等场景。
    """

    name = "update_node"
    description = (
        "更新已有知识节点的内容。当你发现某个节点的描述需要修正、"
        "或对话中产生了新的要点/示例/误区需要补充时，调用此工具完成更新。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "node_id": {"type": "string", "description": "要更新的知识节点 id"},
            "title": {"type": "string", "description": "新标题，不修改则不填"},
            "description": {
                "type": "string",
                "description": "新的简短描述（100字以内），不修改则不填",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "新的标签列表（全量替换），不修改则不填",
            },
            "key_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": "新的核心要点列表（全量替换），不修改则不填",
            },
            "examples": {
                "type": "array",
                "items": {"type": "string"},
                "description": "新的示例/代码列表（全量替换），不修改则不填",
            },
            "common_mistakes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "新的常见误区列表（全量替换），不修改则不填",
            },
            "summary": {
                "type": "string",
                "description": "新的详细总结（支持 Markdown），不修改则不填",
            },
        },
        "required": ["node_id"],
    }

    def __init__(self, db: sqlite3.Connection, user_id: str):
        super().__init__()
        self._db = db
        self._user_id = user_id
        self._repo = NodeRepository(db)

    def run(
        self,
        node_id: str,
        title: str = None,
        description: str = None,
        tags: list[str] = None,
        key_points: list[str] = None,
        examples: list[str] = None,
        common_mistakes: list[str] = None,
        summary: str = None,
    ) -> str:
        # 验证节点归属
        node = self._repo.get_by_id(node_id)
        if not node:
            return json.dumps(
                {"success": False, "message": f"未找到节点 {node_id}"},
                ensure_ascii=False,
            )
        if node.user_id != self._user_id:
            return json.dumps(
                {"success": False, "message": "无权限修改该节点"}, ensure_ascii=False
            )

        # 构造 content 更新：只覆盖传入的字段，其余保留原值
        content_update = None
        if any(v is not None for v in [key_points, examples, common_mistakes, summary]):
            old = node.content
            content_update = NodeContent(
                key_points=key_points if key_points is not None else old.key_points,
                examples=examples if examples is not None else old.examples,
                common_mistakes=common_mistakes
                if common_mistakes is not None
                else old.common_mistakes,
                summary=summary if summary is not None else old.summary,
            )

        update = NodeUpdate(
            title=title,
            description=description,
            tags=tags,
            content=content_update,
        )

        updated = self._repo.update(node_id, update)
        return json.dumps(
            {"success": True, "node_id": updated.id, "title": updated.title},
            ensure_ascii=False,
        )
