"""
知识节点路由
"""

from fastapi import APIRouter, Depends, HTTPException
from models import NodeUpdate, NodeReviewResult, NodeSchema, NodeBrief
from services import MemoryService, NodeService
from dependencies import get_current_user

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("", response_model=list[NodeBrief])
def list_nodes(user_id: str = Depends(get_current_user)):
    return NodeService().list_nodes(user_id)


@router.get("/due", response_model=list[NodeBrief])
def due_today(user_id: str = Depends(get_current_user)):
    return NodeService().list_due_today(user_id)


@router.get("/{node_id}", response_model=NodeSchema)
def get_node(node_id: str, user_id: str = Depends(get_current_user)):
    node = NodeService().get_node(user_id, node_id)
    if not node:
        raise HTTPException(404, "节点不存在")
    return node


@router.patch("/{node_id}", response_model=NodeSchema)
def update_node(
    node_id: str,
    data: NodeUpdate,
    user_id: str = Depends(get_current_user),
):
    node = NodeService().update_node(user_id, node_id, data)
    if not node:
        raise HTTPException(404, "节点不存在")
    return node


@router.delete("/{node_id}", status_code=204)
def delete_node(node_id: str, user_id: str = Depends(get_current_user)):
    ok = NodeService().delete_node(user_id, node_id)
    if not ok:
        raise HTTPException(404, "节点不存在")


@router.post("/{node_id}/review", response_model=dict)
def review_node(
    node_id: str,
    body: NodeReviewResult,
    user_id: str = Depends(get_current_user),
):
    try:
        return MemoryService().review_node_for_user(user_id, node_id, body.quality)
    except ValueError as e:
        raise HTTPException(404, str(e))
