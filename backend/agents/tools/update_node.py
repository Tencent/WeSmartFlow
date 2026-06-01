"""
update_node：Agent 已整理好新内容后，更新知识图谱中某个节点的信息
"""

from __future__ import annotations

import json
from agent_core.tool.base import BaseTool
from models.node import NodeContent, NodeRelation, NodeUpdate
from repositories.node_repo import NodeRepository


class UpdateNodeTool(BaseTool):
    """
    将 Agent 整理好的新内容更新到已有知识节点中。
    可用于：对话中发现节点描述不准确、补充要点、追加示例、纠正常见误区等场景。
    也可用于：为已有节点补充与其他节点的关系（父节点、相关节点、对比节点）。
    """

    name = "update_node"
    description = (
        "更新已有知识节点的内容或关系。当你发现某个节点的描述需要修正、"
        "或对话中产生了新的要点/示例/误区需要补充、"
        "或需要为节点建立与其他节点的关系时，调用此工具完成更新。"
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
            "parent_node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "父节点 id 列表（追加），新节点是这些节点的子概念/需要先掌握这些前置知识，不修改则不填",
            },
            "related_node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "相关节点 id 列表（追加），与当前节点同类或横向关联的节点，会建立双向 related 关系，不修改则不填",
            },
            "contrast_node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "对比节点 id 列表（追加），与当前节点形成对立/对照的节点，会建立双向 contrasts 关系，不修改则不填",
            },
        },
        "required": ["node_id"],
    }

    def __init__(self, user_id: str):
        super().__init__()
        self._user_id = user_id
        self._repo = NodeRepository()

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
        parent_node_ids: list[str] = None,
        related_node_ids: list[str] = None,
        contrast_node_ids: list[str] = None,
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

        # 处理关系追加
        relations_update = None
        if any(v for v in [parent_node_ids, related_node_ids, contrast_node_ids]):
            # 基于已有关系进行追加
            new_relations = list(node.relations)
            # 已有关系的 target_id 集合，避免重复
            existing_targets = {r.target_node_id for r in node.relations}
            # 收集需要更新对端节点的操作
            nodes_to_update: dict[str, NodeUpdate] = {}

            # 父节点：当前节点 → 父节点 prerequisite，父节点 → 当前节点 extends
            for parent_id in parent_node_ids or []:
                if parent_id in existing_targets or parent_id == node_id:
                    continue
                parent = self._repo.get_by_id(parent_id)
                if parent:
                    new_relations.append(
                        NodeRelation(
                            target_node_id=parent_id, relation_type="prerequisite"
                        )
                    )
                    parent_relations = list(parent.relations) + [
                        NodeRelation(target_node_id=node_id, relation_type="extends")
                    ]
                    nodes_to_update[parent_id] = NodeUpdate(relations=parent_relations)
                    existing_targets.add(parent_id)

            # 相关节点：双向 related
            for related_id in related_node_ids or []:
                if related_id in existing_targets or related_id == node_id:
                    continue
                related_node = self._repo.get_by_id(related_id)
                if related_node:
                    new_relations.append(
                        NodeRelation(target_node_id=related_id, relation_type="related")
                    )
                    related_relations = list(related_node.relations) + [
                        NodeRelation(target_node_id=node_id, relation_type="related")
                    ]
                    nodes_to_update[related_id] = NodeUpdate(
                        relations=related_relations
                    )
                    existing_targets.add(related_id)

            # 对比节点：双向 contrasts
            for contrast_id in contrast_node_ids or []:
                if contrast_id in existing_targets or contrast_id == node_id:
                    continue
                contrast_node = self._repo.get_by_id(contrast_id)
                if contrast_node:
                    new_relations.append(
                        NodeRelation(
                            target_node_id=contrast_id, relation_type="contrasts"
                        )
                    )
                    contrast_relations = list(contrast_node.relations) + [
                        NodeRelation(target_node_id=node_id, relation_type="contrasts")
                    ]
                    nodes_to_update[contrast_id] = NodeUpdate(
                        relations=contrast_relations
                    )
                    existing_targets.add(contrast_id)

            # 更新对端节点的关系
            for target_id, target_update in nodes_to_update.items():
                self._repo.update(target_id, target_update)

            relations_update = new_relations

        update = NodeUpdate(
            title=title,
            description=description,
            tags=tags,
            content=content_update,
            relations=relations_update,
        )

        updated = self._repo.update(node_id, update)
        return json.dumps(
            {"success": True, "node_id": updated.id, "title": updated.title},
            ensure_ascii=False,
        )
