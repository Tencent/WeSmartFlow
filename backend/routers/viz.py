"""
交互式可视化（EduViz）API

提供给 /#/eduviz-demo 调试页面以及前端 EduVizSandbox 使用：

- POST /api/viz/generate         同步调用 GenerateInteractiveVizTool 生成可视化
- GET  /api/viz/{viz_id}/meta    拉取可视化元信息（含 documents 记录与 meta.json）
- GET  /api/viz                  列出当前用户名下的所有可视化（按时间倒序）

可视化代码（``viz.js``）通过 ``/api/documents/{viz_id}/raw`` 读取，
不再单独提供 ``/code`` / ``/play`` 端点。
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agents.tools.generate_viz import GenerateInteractiveVizTool
from config import VIZ_DIR
from database import get_db
from dependencies import get_current_user
from repositories.document_repo import DocumentRepository
from utils.validators import UuidPath, sanitize_uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/viz", tags=["viz"])


# ─────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────


class GenerateVizRequest(BaseModel):
    title: str = Field(..., description="可视化标题")
    concept: str = Field(..., description="要让学生理解的核心概念")
    interaction_hint: Optional[str] = Field("", description="建议的交互形式")
    node_ids: Optional[list[str]] = Field(default=None, description="关联的知识节点 ID")
    session_id: Optional[str] = Field(default=None, description="所属会话 ID")


class GenerateVizResponse(BaseModel):
    ok: bool
    viz_id: Optional[str] = None
    error: Optional[str] = None


class VizMeta(BaseModel):
    viz_id: str
    title: str
    concept: str
    interaction_hint: str = ""
    file_size: int = 0
    created_at: Optional[str] = None
    node_ids: list[str] = []


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _assert_viz_owner(viz_id: str, user_id: str) -> None:
    """校验 viz 是否属于当前用户。"""
    with get_db() as conn:
        cur = conn.execute(
            "SELECT user_id, file_type FROM documents WHERE id = ? LIMIT 1",
            (viz_id,),
        )
        row = cur.fetchone()
    if row is None or row["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="可视化不存在")
    if row["file_type"] != "viz":
        raise HTTPException(status_code=404, detail="文档不是可视化类型")


# ─────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────


@router.post("/generate", response_model=GenerateVizResponse)
async def generate_viz(
    payload: GenerateVizRequest,
    user_id: str = Depends(get_current_user),
):
    """同步调用 VizWriterAgent 生成一个交互式可视化。"""
    try:
        tool = GenerateInteractiveVizTool(
            user_id=user_id,
            session_id=payload.session_id,
        )
        result = tool.run(
            title=payload.title,
            concept=payload.concept,
            interaction_hint=payload.interaction_hint or "",
            node_ids=payload.node_ids or [],
        )
    except Exception as e:  # pylint: disable=broad-except
        logger.exception("generate_viz 调用失败")
        return GenerateVizResponse(ok=False, error=f"内部异常: {e}")

    if isinstance(result, str) and result.startswith("Error"):
        return GenerateVizResponse(ok=False, error=result)

    return GenerateVizResponse(ok=True, viz_id=result)


@router.get("/{viz_id}/meta", response_model=VizMeta)
async def get_viz_meta(
    viz_id: UuidPath,
    user_id: str = Depends(get_current_user),
):
    """返回可视化元信息（融合 documents 表 + meta.json）。"""
    # ── 入口显式净化（SAST sanitizer）──
    # 通过 uuid.UUID 解析 + str 重格式化，把外部输入替换为可信字符串。
    # 重新赋值给同名变量后，下游所有引用都指向净化值，污点链在此切断。
    viz_id = sanitize_uuid(viz_id, field_name="viz_id")

    _assert_viz_owner(viz_id, user_id)

    doc_repo = DocumentRepository()
    doc = doc_repo.get_by_id(viz_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="可视化不存在")

    # 双层防御：拼路径后做 resolve + 目录围栏检查，
    # 防止符号链接 / `..` 等极端绕过，确保 meta.json 必落在 VIZ_DIR/<viz_id>/ 之下。
    viz_root = (VIZ_DIR / viz_id).resolve()
    base = VIZ_DIR.resolve()
    if viz_root.parent != base:
        raise HTTPException(status_code=404, detail="可视化不存在")
    meta_path = (viz_root / "meta.json").resolve()
    if meta_path.parent != viz_root:
        raise HTTPException(status_code=404, detail="可视化不存在")

    concept = doc.generation_prompt or ""
    interaction_hint = ""
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            concept = meta.get("concept", concept)
            interaction_hint = meta.get("interaction_hint", "")
        except Exception:  # pylint: disable=broad-except
            pass

    return VizMeta(
        viz_id=doc.id,
        title=doc.title,
        concept=concept,
        interaction_hint=interaction_hint,
        file_size=doc.file_size or 0,
        created_at=doc.created_at,
        node_ids=doc.node_ids or [],
    )


@router.get("", response_model=list[VizMeta])
async def list_viz(
    limit: int = 20,
    user_id: str = Depends(get_current_user),
):
    """列出当前用户的所有可视化（按 created_at 倒序）。"""
    limit = max(1, min(100, int(limit)))
    with get_db() as conn:
        cur = conn.execute(
            """
            SELECT id, title, generation_prompt, file_size, created_at, node_ids
            FROM documents
            WHERE user_id = ? AND file_type = 'viz' AND status = 'ready'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()

    items: list[VizMeta] = []
    for row in rows:
        try:
            node_ids = json.loads(row["node_ids"]) if row["node_ids"] else []
        except Exception:  # pylint: disable=broad-except
            node_ids = []
        items.append(
            VizMeta(
                viz_id=row["id"],
                title=row["title"],
                concept=row["generation_prompt"] or "",
                interaction_hint="",
                file_size=row["file_size"] or 0,
                created_at=row["created_at"],
                node_ids=node_ids,
            )
        )
    return items
