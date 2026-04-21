"""
知识节点路由
"""

import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from database import get_db_dep
from models import NodeCreate, NodeUpdate, NodeReviewResult, NodeSchema, NodeBrief
from repositories import NodeRepository
from repositories.session_repo import SessionRepository
from services import MemoryService

router = APIRouter(prefix="/api/nodes", tags=["nodes"])

USER_ID = "default"  # 单用户模式


@router.get("", response_model=list[NodeBrief])
def list_nodes(db: sqlite3.Connection = Depends(get_db_dep)):
    return NodeRepository(db).get_all(USER_ID)


@router.get("/due", response_model=list[NodeBrief])
def due_today(db: sqlite3.Connection = Depends(get_db_dep)):
    return NodeRepository(db).get_due_today(USER_ID)


@router.get("/{node_id}", response_model=NodeSchema)
def get_node(node_id: str, db: sqlite3.Connection = Depends(get_db_dep)):
    node = NodeRepository(db).get_by_id(node_id)
    if not node:
        raise HTTPException(404, "节点不存在")
    # 为 session 类型的来源填充 source_title（会话 topic 或 title）
    session_repo = SessionRepository(db)
    for origin in node.origins:
        if origin.source_type == "session" and not origin.source_title:
            session = session_repo.get_by_id(origin.source_id)
            if session:
                origin.source_title = session.topic or session.title or None
    return node


@router.post("", response_model=NodeSchema, status_code=201)
def create_node(data: NodeCreate, db: sqlite3.Connection = Depends(get_db_dep)):
    return NodeRepository(db).create(USER_ID, data)


@router.patch("/{node_id}", response_model=NodeSchema)
def update_node(
    node_id: str, data: NodeUpdate, db: sqlite3.Connection = Depends(get_db_dep)
):
    node = NodeRepository(db).update(node_id, data)
    if not node:
        raise HTTPException(404, "节点不存在")
    return node


@router.delete("/{node_id}", status_code=204)
def delete_node(node_id: str, db: sqlite3.Connection = Depends(get_db_dep)):
    ok = NodeRepository(db).delete(node_id)
    if not ok:
        raise HTTPException(404, "节点不存在")


@router.post("/{node_id}/review", response_model=dict)
def review_node(
    node_id: str, body: NodeReviewResult, db: sqlite3.Connection = Depends(get_db_dep)
):
    try:
        return MemoryService(db).review_node(node_id, body.quality)
    except ValueError as e:
        raise HTTPException(404, str(e))
