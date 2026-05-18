"""
NodeService：知识节点的业务门面（facade）。

把 routers/nodes.py 里散落的业务装饰逻辑（如 session origin 的 source_title 回填）、
以及跨 repo 的常用组合，集中在这里。router 只负责 HTTP 契约和异常翻译。
"""

from __future__ import annotations


from models.node import NodeCreate, NodeUpdate, NodeSchema, NodeBrief
from repositories import NodeRepository
from repositories.session_repo import SessionRepository


class NodeService:
    def __init__(self):
        self.node_repo = NodeRepository()
        self.session_repo = SessionRepository()

    # ── 权属校验 ──────────────────────────────────────
    def _assert_owner(self, user_id: str, node_id: str) -> NodeSchema | None:
        """断言节点存在且属于该用户；不存在或不属于该用户都返回 None
        （上层统一翻译为 404，避免通过状态码区分'不存在 vs 不属于你'）。"""
        node = self.node_repo.get_by_id(node_id)
        if not node or node.user_id != user_id:
            return None
        return node

    # ── 读 ────────────────────────────────────────────
    def list_nodes(self, user_id: str) -> list[NodeBrief]:
        return self.node_repo.get_all(user_id)

    def list_due_today(self, user_id: str) -> list[NodeBrief]:
        return self.node_repo.get_due_today(user_id)

    def get_node(self, user_id: str, node_id: str) -> NodeSchema | None:
        """获取节点（仅限本人），并为 session 类型 origin 回填 source_title。"""
        node = self._assert_owner(user_id, node_id)
        if not node:
            return None
        for origin in node.origins:
            if origin.source_type == "session" and not origin.source_title:
                session = self.session_repo.get_by_id(origin.source_id)
                if session:
                    origin.source_title = session.topic or session.title or None
        return node

    # ── 写 ────────────────────────────────────────────
    def create_node(self, user_id: str, data: NodeCreate) -> NodeSchema:
        return self.node_repo.create(user_id, data)

    def update_node(
        self, user_id: str, node_id: str, data: NodeUpdate
    ) -> NodeSchema | None:
        if not self._assert_owner(user_id, node_id):
            return None
        return self.node_repo.update(node_id, data)

    def delete_node(self, user_id: str, node_id: str) -> bool:
        if not self._assert_owner(user_id, node_id):
            return False
        return self.node_repo.delete(node_id)
