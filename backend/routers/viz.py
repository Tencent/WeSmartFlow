"""
交互式可视化（EduViz）API

提供给 /#/eduviz-demo 调试页面以及前端 EduVizSandbox 使用：

- POST /api/viz/generate         同步调用 GenerateInteractiveVizTool 生成可视化
- GET  /api/viz/{viz_id}/code    拉取已生成的 viz.js 源代码（纯文本）
- GET  /api/viz/{viz_id}/meta    拉取可视化的元信息（含数据库记录与 meta.json）
- GET  /api/viz                  列出当前用户名下的所有可视化（按时间倒序）

权属校验：viz_id 即 documents.id，校验 documents.user_id 是否匹配当前用户。
"""

from __future__ import annotations

import html
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from agents.tools.generate_viz import GenerateInteractiveVizTool
from config import ROOT_DIR, VIZ_DIR
from database import get_db
from dependencies import decode_access_token, get_current_user
from repositories.document_repo import DocumentRepository

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


def _get_viz_request_user(request: Request) -> tuple[str, str | None]:
    """
    viz 播放页鉴权：
    - 小程序普通请求可带 Authorization header；
    - web-view 无法注入 header，所以支持 ?token=xxx；
    - 后续同域请求可通过 cookie 兜底。
    """
    auth = request.headers.get("authorization") or ""
    token = None
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    query_token = request.query_params.get("token")
    if not token:
        token = query_token or request.cookies.get("ascendflow_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_access_token(token), query_token


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
    """
    同步调用 VizWriterAgent 生成一个交互式可视化。

    注意：内部会跑 ReActAgent（写代码 + 校验 + 修复），耗时通常几秒到几十秒，
    前端应给出 loading 状态。
    """
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


@router.get("/{viz_id}/code", response_class=PlainTextResponse)
async def get_viz_code(
    viz_id: str,
    user_id: str = Depends(get_current_user),
):
    """返回 viz.js 源代码（text/javascript）。"""
    _assert_viz_owner(viz_id, user_id)

    viz_file = VIZ_DIR / viz_id / "viz.js"
    if not viz_file.exists():
        raise HTTPException(status_code=404, detail="viz.js 文件不存在")

    return PlainTextResponse(
        content=viz_file.read_text(encoding="utf-8"),
        media_type="text/javascript; charset=utf-8",
    )


@router.get("/{viz_id}/play", response_class=HTMLResponse)
async def play_viz(
    viz_id: str,
    request: Request,
):
    """返回可在小程序 web-view 中直接播放的 EduViz HTML 页面。"""
    user_id, query_token = _get_viz_request_user(request)
    _assert_viz_owner(viz_id, user_id)

    viz_file = VIZ_DIR / viz_id / "viz.js"
    if not viz_file.exists():
        raise HTTPException(status_code=404, detail="viz.js 文件不存在")

    sdk_path = ROOT_DIR / "frontend" / "src" / "components" / "EduViz" / "eduviz-sdk.js"
    if not sdk_path.exists():
        raise HTTPException(status_code=500, detail="EduViz SDK 缺失")

    meta_title = "交互可视化"
    meta_path = VIZ_DIR / viz_id / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta_title = meta.get("title") or meta_title
        except Exception:  # pylint: disable=broad-except
            pass

    sdk_source = sdk_path.read_text(encoding="utf-8")
    viz_code = viz_file.read_text(encoding="utf-8")
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <title>{html.escape(meta_title)}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
  <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ min-height: 100%; background: #0f1117; color: #f7f7fb; font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; overflow: auto; }}
    body {{ padding: 10px; }}
    canvas, svg {{ max-width: 100%; }}
    .ev-error {{ margin: 12px; padding: 12px; color: #ef4444; background: rgba(239,68,68,.12); border: 1px solid rgba(239,68,68,.3); border-radius: 8px; white-space: pre-wrap; }}
  </style>
</head>
<body>
  <script>{sdk_source}</script>
  <script>
    document.documentElement.setAttribute('data-theme', 'dark');
    if (window.EduViz && typeof window.EduViz.setTheme === 'function') window.EduViz.setTheme('dark');
    window.onerror = function(msg, url, line, col, err) {{
      var div = document.createElement('div');
      div.className = 'ev-error';
      div.textContent = '可视化运行错误：' + msg;
      document.body.appendChild(div);
      return true;
    }};
    window.onunhandledrejection = function(event) {{
      var div = document.createElement('div');
      div.className = 'ev-error';
      div.textContent = '可视化运行错误：' + ((event.reason && event.reason.message) || event.reason || 'Unknown');
      document.body.appendChild(div);
      event.preventDefault();
    }};
    (async function() {{
{viz_code}
    }})();
  </script>
</body>
</html>"""
    headers = {}
    if query_token:
        headers["Set-Cookie"] = (
            f"ascendflow_token={query_token}; Path=/; HttpOnly; SameSite=Lax"
        )
    return HTMLResponse(content=page, headers=headers)


@router.get("/{viz_id}/meta", response_model=VizMeta)
async def get_viz_meta(
    viz_id: str,
    user_id: str = Depends(get_current_user),
):
    """返回可视化元信息（融合 documents 表 + meta.json）。"""
    _assert_viz_owner(viz_id, user_id)

    doc_repo = DocumentRepository()
    doc = doc_repo.get_by_id(viz_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="可视化不存在")

    # 读 meta.json 拿 concept / interaction_hint（生成时写入的细节）
    meta_path = VIZ_DIR / viz_id / "meta.json"
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
