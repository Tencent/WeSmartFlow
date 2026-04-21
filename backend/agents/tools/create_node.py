"""
create_node：Agent 在知识图谱中创建新的知识节点

包含三个类：
- BaseCreateNodeTool     公共逻辑基类（模板方法模式）
- SessionCreateNodeTool  来源为会话（对话中动态提取知识点）
- DocumentCreateNodeTool 来源为文档（解析上传文档时批量创建）
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import sqlite3
from abc import abstractmethod
from agent_core.tool.base import BaseTool
from models.node import NodeCreate, NodeContent, NodeOrigin, NodeRelation, NodeUpdate
from repositories.node_repo import NodeRepository


class BaseCreateNodeTool(BaseTool):
    """
    创建知识节点的抽象基类。
    子类只需实现 _get_origins() 返回对应来源列表。
    """

    name = "create_node"
    description = (
        "在用户知识图谱中创建一个新的知识节点。"
        "每个节点必须是一个单一、独立的知识概念。"
        "通过 parent_node_ids / related_node_ids / contrast_node_ids 与已有节点建立关系。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": (
                    "节点标题，必须是单一概念，如「极限」「导数」「二叉树」。"
                    "禁止使用复合标题（如「极限和导数」「栈与队列」），"
                    "多个概念应分别创建节点并用关系连接。"
                ),
            },
            "description": {
                "type": "string",
                "description": "节点的简短描述，说明这个知识点的核心内容，100字以内",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": '标签列表，用于分类，如 ["数据结构", "算法"]',
            },
            "key_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": '该知识点的核心要点列表，如 ["左子树所有值小于根节点", "中序遍历结果有序"]',
            },
            "examples": {
                "type": "array",
                "items": {"type": "string"},
                "description": "示例/代码列表",
            },
            "common_mistakes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "常见误区列表",
            },
            "summary": {
                "type": "string",
                "description": "对该知识点的详细总结，支持 Markdown，可包含代码示例",
            },
            "parent_node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "父节点 id 列表，新节点是这些节点的子概念/需要先掌握这些前置知识（支持多个父节点，如「卷积神经网络」的父节点可以是「神经网络」和「卷积运算」）",
            },
            "related_node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "相关节点 id 列表，与新节点同类或横向关联的已有节点（如同类算法），会建立双向 related 关系",
            },
            "contrast_node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "对比节点 id 列表，与新节点形成明显对立/对照的已有节点（如「递归」vs「迭代」、「有序」vs「无序」），会建立双向 contrasts 关系",
            },
        },
        "required": ["title", "description"],
    }

    def __init__(self, db: sqlite3.Connection, user_id: str, on_result_hook=None):
        super().__init__(on_result_hook=on_result_hook)
        self._db = db
        self._user_id = user_id
        self._repo = NodeRepository(db)

    @abstractmethod
    def _get_origins(self, description: str) -> list[NodeOrigin]:
        """返回该节点的来源列表，子类实现"""
        ...

    def run(
        self,
        title: str,
        description: str,
        tags: list[str] = None,
        key_points: list[str] = None,
        examples: list[str] = None,
        common_mistakes: list[str] = None,
        summary: str = "",
        parent_node_ids: list[str] = None,
        related_node_ids: list[str] = None,
        contrast_node_ids: list[str] = None,
    ) -> str:
        # 检查同名节点是否已存在，避免重复创建
        existing = self._db.execute(
            "SELECT id FROM nodes WHERE user_id=? AND title=?", (self._user_id, title)
        ).fetchone()
        if existing:
            return json.dumps(
                {
                    "node_id": existing["id"],
                    "created": False,
                    "message": f"节点「{title}」已存在，跳过创建。",
                },
                ensure_ascii=False,
            )

        node = self._repo.create(
            self._user_id,
            NodeCreate(
                title=title,
                description=description,
                tags=tags or [],
                content=NodeContent(
                    key_points=key_points or [],
                    examples=examples or [],
                    common_mistakes=common_mistakes or [],
                    summary=summary,
                ),
                origins=self._get_origins(description),
            ),
        )

        self._db.commit()

        new_relations = list(node.relations)
        # 已处理过的节点 id 集合，防止同一节点被多种关系重复处理
        processed_ids: set[str] = set()

        # 收集所有需要更新的节点关系
        nodes_to_update = {}

        # 父节点：新节点 → 父节点 prerequisite，父节点 → 新节点 extends（不对称）
        for parent_id in parent_node_ids or []:
            if parent_id in processed_ids:
                continue
            parent = self._repo.get_by_id(parent_id)
            if parent:
                new_relations.append(
                    NodeRelation(target_node_id=parent_id, relation_type="prerequisite")
                )
                parent_relations = list(parent.relations) + [
                    NodeRelation(target_node_id=node.id, relation_type="extends")
                ]
                nodes_to_update[parent_id] = NodeUpdate(relations=parent_relations)
                processed_ids.add(parent_id)

        # 相关节点：双向 related（对称）
        for related_id in related_node_ids or []:
            if related_id in processed_ids:
                continue
            related_node = self._repo.get_by_id(related_id)
            if related_node:
                new_relations.append(
                    NodeRelation(target_node_id=related_id, relation_type="related")
                )
                related_relations = list(related_node.relations) + [
                    NodeRelation(target_node_id=node.id, relation_type="related")
                ]
                nodes_to_update[related_id] = NodeUpdate(relations=related_relations)
                processed_ids.add(related_id)

        # 对比节点：双向 contrasts（对称）
        for contrast_id in contrast_node_ids or []:
            if contrast_id in processed_ids:
                continue
            contrast_node = self._repo.get_by_id(contrast_id)
            if contrast_node:
                new_relations.append(
                    NodeRelation(target_node_id=contrast_id, relation_type="contrasts")
                )
                contrast_relations = list(contrast_node.relations) + [
                    NodeRelation(target_node_id=node.id, relation_type="contrasts")
                ]
                nodes_to_update[contrast_id] = NodeUpdate(relations=contrast_relations)
                processed_ids.add(contrast_id)

        # 统一更新新节点的所有关系
        if new_relations:
            nodes_to_update[node.id] = NodeUpdate(relations=new_relations)

        # 在一个事务中批量更新所有节点关系
        if nodes_to_update:
            for node_id, update_data in nodes_to_update.items():
                self._repo.update(node_id, update_data)
            # 手动提交事务，确保所有关系更新在一个事务中完成
            self._db.commit()

        linked_count = len(new_relations)
        result = {
            "node_id": node.id,
            "created": True,
            "title": node.title,
            "linked_relations": linked_count,
        }
        # 软提醒：如果没有建立任何关系，提示 Agent 这是孤立节点
        if linked_count == 0:
            result["warning"] = (
                "该节点没有与任何已有节点建立关系，已成为孤立节点。"
                "建议用 search_nodes 搜索相关节点后，用 update_node 补充关系。"
            )
        return json.dumps(result, ensure_ascii=False)


class SessionCreateNodeTool(BaseCreateNodeTool):
    """来源为对话会话，用于对话中动态提取并创建知识节点。"""

    def __init__(
        self, db: sqlite3.Connection, user_id: str, session_id: str, on_result_hook=None
    ):
        super().__init__(db, user_id, on_result_hook=on_result_hook)
        self._session_id = session_id

    def _get_origins(self, description: str) -> list[NodeOrigin]:
        return [
            NodeOrigin(
                source_type="session",
                source_id=self._session_id,
                location=f"会话 {self._session_id[:8]}",
                excerpt=description[:200],
            )
        ]


class DocumentCreateNodeTool(BaseCreateNodeTool):
    """来源为上传文档，用于解析文档时批量提取并创建知识节点。"""

    def __init__(
        self,
        db: sqlite3.Connection,
        user_id: str,
        document_id: str,
        location: str = "",
        excerpt: str = "",
        on_result_hook=None,
    ):
        super().__init__(db, user_id, on_result_hook=on_result_hook)
        self._document_id = document_id
        self._location = location
        self._excerpt = excerpt

    def _get_origins(self, description: str) -> list[NodeOrigin]:
        return [
            NodeOrigin(
                source_type="document",
                source_id=self._document_id,
                location=self._location,
                excerpt=(self._excerpt or description)[:200],
            )
        ]
