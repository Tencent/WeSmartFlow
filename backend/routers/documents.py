"""
文档路由（上传 + 提取节点 + 节点挂接 + 文件读取）。

本层只负责：
  - 接收 HTTP / form 参数
  - 调用 DocumentService 执行业务
  - 把 Service 抛出的业务异常翻译成 HTTPException

文件读取走两个统一端点：
  - GET /api/documents/{doc_id}/raw           — 主资源
  - GET /api/documents/{doc_id}/asset/{sub}   — 同目录伴生文件
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    BackgroundTasks,
    Body,
)
from fastapi.responses import FileResponse

from models.document import DocumentSchema, DocumentBrief
from services import DocumentService
from services.document_service import (
    DocumentNotFound,
    DocumentNotReady,
    InvalidUpload,
    NodeAlreadyLinked,
    NodeNotFound,
)
from services.document_resolver import (
    AssetPathInvalid,
    DocumentNotFound as ResolverNotFound,
    resolve_asset,
    resolve_main,
)
from utils.web_auth import COOKIE_NAME, get_user_from_request_flexible
from dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


# ── MIME / 响应辅助 ──────────────────────────────────────────────────

_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".tex": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
}


def _infer_mime(path: Path) -> str:
    return _MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _file_response(
    abs_path: Path,
    *,
    query_token: str | None = None,
    download_filename: str | None = None,
) -> FileResponse:
    """统一的文件响应：自动推断 MIME，可选写 Cookie / Content-Disposition。"""
    headers: dict[str, str] = {}
    if query_token:
        # iframe / web-view 首次以 ?token= 打开主资源后，子资源请求由 cookie 兜底
        headers["Set-Cookie"] = (
            f"{COOKIE_NAME}={query_token}; Path=/; HttpOnly; SameSite=Lax"
        )
    return FileResponse(
        path=abs_path,
        media_type=_infer_mime(abs_path),
        filename=download_filename,
        headers=headers,
    )


# ── 文档列表 / 详情 / 上传 / 删除 / 节点挂接 ─────────────────────────


@router.get("", response_model=list[DocumentBrief])
def list_documents(user_id: str = Depends(get_current_user)):
    return DocumentService().list_documents(user_id)


@router.get("/{doc_id}", response_model=DocumentSchema)
def get_document(doc_id: str, user_id: str = Depends(get_current_user)):
    try:
        return DocumentService().get_document(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")


@router.post("/upload", response_model=DocumentSchema, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """上传文档（单文件），后台自动触发提取。"""
    content = await file.read()
    try:
        return await DocumentService().upload(
            user_id=user_id,
            filename=file.filename,
            content=content,
            background_tasks=background_tasks,
        )
    except InvalidUpload as e:
        raise HTTPException(400, str(e))


@router.post("/{doc_id}/extract")
async def trigger_extract(
    doc_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
):
    """手动触发（重新）提取。"""
    try:
        return DocumentService().trigger_extract(user_id, doc_id, background_tasks)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")


@router.get("/{doc_id}/content")
async def get_document_content(doc_id: str, user_id: str = Depends(get_current_user)):
    """获取文档内容（支持分段获取）。"""
    try:
        return DocumentService().get_content(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    except DocumentNotReady:
        raise HTTPException(400, "文档尚未处理完成")


# ── 文件读取（核心两个接口） ──────────────────────────────────────────


@router.api_route("/{doc_id}/raw", methods=["GET", "HEAD"])
async def get_document_raw(doc_id: str, request: Request):
    """读取文档主资源。

    URL 参数：
      - ``token`` — 可选；为 iframe / web-view 兜底鉴权。命中后会写同域 cookie。
      - ``download=1`` — 强制 ``Content-Disposition: attachment``，触发浏览器下载。
    """
    user_id, query_token = get_user_from_request_flexible(request)
    try:
        rf = resolve_main(doc_id, user_id)
    except ResolverNotFound:
        raise HTTPException(404, "文件不存在")

    download = request.query_params.get("download") in {"1", "true", "yes"}
    return _file_response(
        rf.abs_path,
        query_token=query_token,
        download_filename=rf.doc.file_name if download else None,
    )


@router.api_route("/{doc_id}/asset/{sub_path:path}", methods=["GET", "HEAD"])
async def get_document_asset(doc_id: str, sub_path: str, request: Request):
    """读取文档主资源同目录下的伴生文件。

    例如 HTML 卡片 ``card.html`` 内嵌图片：
      ``/api/documents/{doc_id}/asset/images/cover.png``

    沉浸式课程章节音频帧：
      ``/api/documents/{audio_doc_id}/asset/frame_001.wav``
    """
    user_id, query_token = get_user_from_request_flexible(request)
    try:
        rf = resolve_asset(doc_id, sub_path, user_id)
    except (ResolverNotFound, AssetPathInvalid):
        raise HTTPException(404, "文件不存在")
    return _file_response(rf.abs_path, query_token=query_token)


# ── 删除 / 节点挂接 ──────────────────────────────────────────────────


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, user_id: str = Depends(get_current_user)):
    try:
        DocumentService().delete(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/{doc_id}/nodes")
async def get_document_nodes(doc_id: str, user_id: str = Depends(get_current_user)):
    """获取文档关联的知识节点。"""
    try:
        return DocumentService().list_document_nodes(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")


@router.get("/nodes/{node_id}/documents")
async def get_node_documents(node_id: str, user_id: str = Depends(get_current_user)):
    """获取知识节点关联的文档。"""
    try:
        return DocumentService().list_node_documents(user_id, node_id)
    except NodeNotFound:
        raise HTTPException(404, "知识节点不存在")


@router.get("/{doc_id}/summary")
async def get_document_summary(doc_id: str, user_id: str = Depends(get_current_user)):
    """获取文档摘要信息。"""
    try:
        return DocumentService().get_summary(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    except DocumentNotReady:
        raise HTTPException(400, "文档尚未处理完成")


@router.post("/{doc_id}/add_node")
async def add_node_to_document(
    doc_id: str,
    node_id: str = Body(..., embed=True),
    user_id: str = Depends(get_current_user),
):
    """为文档手动添加现有节点。"""
    try:
        return DocumentService().add_node(user_id, doc_id, node_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    except NodeNotFound:
        raise HTTPException(404, "节点不存在")
    except NodeAlreadyLinked:
        raise HTTPException(400, "节点已关联到该文档")
