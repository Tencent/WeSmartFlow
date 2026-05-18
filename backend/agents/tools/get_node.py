"""
get_node：按 id 查询知识节点的完整详情
"""

from __future__ import annotations

import json
from agent_core.tool.base import BaseTool
from repositories.node_repo import NodeRepository


class GetNodeTool(BaseTool):
    """
    按节点 id 获取完整的知识节点详情，包括核心要点、示例、常见误区、详细总结等。
    通常在 search_nodes 找到目标节点后，需要查看完整内容时调用。
    """

    name = "get_node"
    description = (
        "按节点 id 获取知识节点的完整详情，包括 key_points、examples、"
        "common_mistakes、summary 等全部内容。"
        "在 search_nodes 找到节点 id 后，需要查看完整内容时调用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "node_id": {"type": "string", "description": "要查询的知识节点 id"}
        },
        "required": ["node_id"],
    }

    def __init__(self, user_id: str):
        super().__init__()
        self._user_id = user_id
        self._repo = NodeRepository()

    def run(self, node_id: str) -> str:
        node = self._repo.get_by_id(node_id)
        if not node:
            return json.dumps(
                {"success": False, "message": f"未找到节点 {node_id}"},
                ensure_ascii=False,
            )
        if node.user_id != self._user_id:
            return json.dumps(
                {"success": False, "message": "无权限查看该节点"}, ensure_ascii=False
            )

        result = {
            "id": node.id,
            "title": node.title,
            "description": node.description,
            "tags": node.tags,
            "content": {
                "key_points": node.content.key_points,
                "examples": node.content.examples,
                "common_mistakes": node.content.common_mistakes,
                "summary": node.content.summary,
            },
            "mastery_level": node.memory.mastery_level,
            "due_date": node.memory.due_date.isoformat()
            if node.memory.due_date
            else None,
            "created_at": node.created_at.isoformat(),
            "updated_at": node.updated_at.isoformat(),
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
