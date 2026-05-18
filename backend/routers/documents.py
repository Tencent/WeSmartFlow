"""
文档路由（上传 + 提取节点 + 节点挂接）。

本层只负责：
  - 接收 HTTP / form 参数
  - 调用 DocumentService 执行业务
  - 把 Service 抛出的业务异常翻译成 HTTPException
"""

from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
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
from dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


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


@router.get("/{doc_id}/download")
async def download_document(doc_id: str, user_id: str = Depends(get_current_user)):
    """下载文档原文件。"""
    try:
        file_path, file_name = DocumentService().get_download_info(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    return FileResponse(
        path=file_path, filename=file_name, media_type="application/octet-stream"
    )


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
