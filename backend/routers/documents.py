"""
文档路由（上传 + 提取节点）
"""

from __future__ import annotations

import logging
import shutil
import sqlite3

from pathlib import Path
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
from config import UPLOADS_DIR, ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_MB
from database import get_db_dep
from models.document import DocumentSchema, DocumentBrief
from repositories import DocumentRepository
from repositories.base import new_id
from services import ExtractService


logger = logging.getLogger(__file__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

USER_ID = "default"


@router.get("", response_model=list[DocumentBrief])
def list_documents(db: sqlite3.Connection = Depends(get_db_dep)):
    return DocumentRepository(db).get_all(USER_ID)


@router.get("/{doc_id}", response_model=DocumentSchema)
def get_document(doc_id: str, db: sqlite3.Connection = Depends(get_db_dep)):
    doc = DocumentRepository(db).get_by_id(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    return doc


@router.post("/upload", response_model=DocumentSchema, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: sqlite3.Connection = Depends(get_db_dep),
):
    """上传文档（单文件），后台自动触发提取"""
    # 文件类型验证
    file_ext = file.filename.split(".")[-1] if "." in file.filename else "txt"
    if f".{file_ext}" not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"不支持的文件类型: {file_ext}，支持的类型: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # 文件大小验证
    content = await file.read()
    max_size_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_size_bytes:
        raise HTTPException(400, f"文件大小超过限制: {MAX_UPLOAD_SIZE_MB}MB")

    # 生成文档ID和文件名
    doc_id = new_id()
    file_name = f"{doc_id}.{file_ext}"

    # 创建存储目录
    save_dir = UPLOADS_DIR / doc_id
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / file_name

    # 保存文件
    file_path.write_bytes(content)

    # 创建文档记录
    doc_repo = DocumentRepository(db)
    doc = doc_repo.create(
        doc_id=doc_id,
        user_id=USER_ID,
        title=file.filename,
        source="uploaded",
        file_name=file_name,
        file_type=file_ext,
        file_size=len(content),
    )

    # 手动提交事务，确保文档创建成功
    db.commit()

    # 后台处理提取 - 使用异步版本以获得更好的性能
    background_tasks.add_task(_extract_background, doc.id)

    return doc


async def _extract_background(doc_id: str):
    """后台任务：提取知识节点（异步版本，性能更好）"""
    import logging
    from database import get_db

    logger = logging.getLogger(__name__)

    logger.info("开始后台提取任务，文档ID: %s", doc_id)

    try:
        # 使用上下文管理器确保数据库连接正确管理
        with get_db() as conn:
            extract_service = ExtractService(conn)
            logger.info("ExtractService创建成功，开始提取文档 %s", doc_id)
            await extract_service.extract(USER_ID, doc_id)
            logger.info("文档 %s 提取任务完成", doc_id)
    except Exception as e:  # pylint: disable=broad-except
        # 记录错误但不要影响主流程
        logger.exception("异步文档提取失败: %s, 错误: %s", doc_id, e)
        logger.error("详细错误信息: %s", str(e))


@router.post("/{doc_id}/extract")
async def trigger_extract(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: sqlite3.Connection = Depends(get_db_dep),
):
    """手动触发（重新）提取"""
    doc = DocumentRepository(db).get_by_id(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    background_tasks.add_task(_extract_background, doc_id)
    return {"message": "提取任务已启动", "doc_id": doc_id}


@router.get("/{doc_id}/content")
async def get_document_content(
    doc_id: str,
    db: sqlite3.Connection = Depends(get_db_dep),
):
    """获取文档内容（支持分段获取）"""
    logger.info("请求获取文档内容，文档ID: %s", doc_id)

    doc = DocumentRepository(db).get_by_id(doc_id)
    if not doc:
        logger.error("文档 %s 在数据库中不存在", doc_id)
        raise HTTPException(404, "文档不存在")

    logger.info("找到文档: id=%s, title=%s, status=%s", doc.id, doc.title, doc.status)

    # 允许 ready 和 failed 状态的文档查看内容
    if doc.status not in ["ready", "failed"]:
        logger.warning("文档 %s 状态为 %s，尚未处理完成", doc_id, doc.status)
        raise HTTPException(400, "文档尚未处理完成")

    # 使用动态文件路径解析
    file_path = Path(doc.get_file_path())
    logger.info("文档文件路径: %s", file_path)

    if not file_path.exists():
        logger.error("文件不存在: %s", file_path)
        raise HTTPException(404, "文件不存在")

    logger.info("文件存在，开始读取内容")

    # 使用ExtractService读取内容和分段
    extract_service = ExtractService(db)
    content = extract_service._read_file(str(file_path), doc.file_type)
    segments = extract_service._segment_document(content, doc.file_type)

    logger.info(
        "成功读取文档内容，长度: %d 字符，分段数: %d", len(content), len(segments)
    )

    return {"content": content, "total_pages": doc.total_pages, "segments": segments}


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: str,
    db: sqlite3.Connection = Depends(get_db_dep),
):
    """下载文档原文件"""
    doc = DocumentRepository(db).get_by_id(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")

    # 使用动态文件路径解析
    file_path = Path(doc.get_file_path())
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")

    return FileResponse(
        path=file_path, filename=doc.file_name, media_type="application/octet-stream"
    )


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, db: sqlite3.Connection = Depends(get_db_dep)):
    doc = DocumentRepository(db).get_by_id(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    # 删除文件
    file_path = Path(doc.get_file_path())
    if file_path.parent.exists():
        shutil.rmtree(file_path.parent, ignore_errors=True)
    DocumentRepository(db).delete(doc_id)


@router.get("/{doc_id}/nodes")
async def get_document_nodes(
    doc_id: str,
    db: sqlite3.Connection = Depends(get_db_dep),
):
    """获取文档关联的知识节点"""
    doc = DocumentRepository(db).get_by_id(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")

    # 获取关联的节点信息
    from repositories.node_repo import NodeRepository

    node_repo = NodeRepository(db)

    nodes = []
    for node_id in doc.node_ids:
        node = node_repo.get_by_id(node_id)
        if node:
            # 找到该节点中来自当前文档的origin
            doc_origin = None
            for origin in node.origins:
                if origin.source_type == "document" and origin.source_id == doc_id:
                    doc_origin = origin
                    break

            nodes.append(
                {
                    "node_id": node.id,
                    "title": node.title,
                    "description": node.description,
                    "origin": doc_origin.dict() if doc_origin else None,
                }
            )

    return {"document_id": doc_id, "document_title": doc.title, "nodes": nodes}


@router.get("/nodes/{node_id}/documents")
async def get_node_documents(
    node_id: str,
    db: sqlite3.Connection = Depends(get_db_dep),
):
    """获取知识节点关联的文档"""
    from repositories.node_repo import NodeRepository

    node_repo = NodeRepository(db)

    node = node_repo.get_by_id(node_id)
    if not node:
        raise HTTPException(404, "知识节点不存在")

    # 获取关联的文档信息
    doc_repo = DocumentRepository(db)
    documents = []

    for origin in node.origins:
        if origin.source_type == "document":
            doc = doc_repo.get_by_id(origin.source_id)
            if doc:
                documents.append(
                    {
                        "document_id": doc.id,
                        "title": doc.title,
                        "source": doc.source,
                        "file_type": doc.file_type,
                        "origin": origin.dict(),
                    }
                )

    return {"node_id": node_id, "node_title": node.title, "documents": documents}


@router.get("/{doc_id}/summary")
async def get_document_summary(
    doc_id: str,
    db: sqlite3.Connection = Depends(get_db_dep),
):
    """获取文档摘要信息"""
    doc = DocumentRepository(db).get_by_id(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")

    if doc.status != "ready":
        raise HTTPException(400, "文档尚未处理完成")

    # 获取关联的节点信息
    from repositories.node_repo import NodeRepository

    node_repo = NodeRepository(db)

    # 统计节点信息
    node_stats = {
        "total_nodes": len(doc.node_ids),
        "concept_nodes": 0,
        "example_nodes": 0,
        "other_nodes": 0,
    }

    for node_id in doc.node_ids:
        node = node_repo.get_by_id(node_id)
        if node:
            # 根据节点内容判断类型
            if node.content.examples:
                node_stats["example_nodes"] += 1
            else:
                node_stats["concept_nodes"] += 1

    # 生成内容摘要（前200字符）
    try:
        extract_service = ExtractService(db)
        file_path = Path(doc.get_file_path())
        content = extract_service._read_file(str(file_path), doc.file_type)
        content_preview = content[:200] + "..." if len(content) > 200 else content
    except Exception:  # pylint: disable=broad-except
        content_preview = "无法读取内容"

    return {
        "document_id": doc_id,
        "title": doc.title,
        "file_type": doc.file_type,
        "file_size": doc.file_size,
        "status": doc.status,
        "created_at": doc.created_at,
        "node_stats": node_stats,
        "content_preview": content_preview,
        "total_pages": doc.total_pages if hasattr(doc, "total_pages") else None,
    }


@router.post("/{doc_id}/add_node")
async def add_node_to_document(
    doc_id: str,
    node_id: str = Body(..., embed=True),
    db: sqlite3.Connection = Depends(get_db_dep),
):
    """为文档手动添加现有节点"""
    doc = DocumentRepository(db).get_by_id(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")

    # 检查节点是否存在
    from repositories.node_repo import NodeRepository
    from models.node import NodeUpdate

    node_repo = NodeRepository(db)
    node = node_repo.get_by_id(node_id)
    if not node:
        raise HTTPException(404, "节点不存在")

    # 检查节点是否已经关联到文档
    if node_id in doc.node_ids:
        raise HTTPException(400, "节点已关联到该文档")

    # 为节点添加文档来源
    from models.node import NodeOrigin

    origin = NodeOrigin(
        source_type="document",
        source_id=doc_id,
        source_title=doc.title,
        source_description=f"来自文档: {doc.title}",
    )

    # 更新节点的来源信息
    updated_origins = node.origins + [origin]
    node_repo.update(node_id, NodeUpdate(origins=updated_origins))

    # 更新文档的节点列表
    updated_node_ids = doc.node_ids + [node_id]
    DocumentRepository(db).set_node_ids(doc_id, updated_node_ids)

    db.commit()

    return {"message": "节点已成功添加到文档", "doc_id": doc_id, "node_id": node_id}
