"""
DocumentService：文档相关业务门面。

负责：
- 文档列表 / 详情 / 删除
- 文件上传（含落盘、大小校验、repo.create、后台提取调度）
- 文档内容读取（read_and_segment）与摘要
- 文档 ↔ 节点的双向关联查询 / 手动挂接

router 层只负责 HTTP 契约和异常翻译。
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks

from config import UPLOADS_DIR, ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_MB
from models.document import DocumentSchema, DocumentBrief
from models.node import NodeOrigin, NodeUpdate
from repositories import DocumentRepository, NodeRepository
from repositories.base import new_id
from services.extract_service import ExtractService

logger = logging.getLogger(__name__)


class DocumentNotFound(Exception):
    """文档不存在。"""


class DocumentNotReady(Exception):
    """文档尚未处理完成。"""


class InvalidUpload(Exception):
    """上传非法（类型 / 大小等）。"""


class NodeNotFound(Exception):
    pass


class NodeAlreadyLinked(Exception):
    pass


class DocumentService:
    def __init__(self):
        self.doc_repo = DocumentRepository()
        self.node_repo = NodeRepository()

    # ── 权属校验 ──────────────────────────────────────
    def _assert_doc_owner(self, user_id: str, doc_id: str) -> DocumentSchema:
        """断言文档存在且属于该用户；否则抛 DocumentNotFound
        （不存在 vs 不属于你 都返回同一异常，避免侧信道泄漏）。"""
        doc = self.doc_repo.get_by_id(doc_id)
        if not doc or doc.user_id != user_id:
            raise DocumentNotFound(doc_id)
        return doc

    def _assert_node_owner(self, user_id: str, node_id: str):
        """断言节点存在且属于该用户；否则抛 NodeNotFound。"""
        node = self.node_repo.get_by_id(node_id)
        if not node or node.user_id != user_id:
            raise NodeNotFound(node_id)
        return node

    # ── 列表 / 详情 ─────────────────────────────────────
    def list_documents(self, user_id: str) -> list[DocumentBrief]:
        return self.doc_repo.get_all(user_id)

    def get_document(self, user_id: str, doc_id: str) -> DocumentSchema:
        return self._assert_doc_owner(user_id, doc_id)

    # ── 上传 ─────────────────────────────────────────────
    async def upload(
        self,
        user_id: str,
        filename: str,
        content: bytes,
        background_tasks: BackgroundTasks,
    ) -> DocumentSchema:
        """处理上传：类型/大小校验 → 落盘 → 建库记录 → 调度后台提取。"""
        file_ext = filename.split(".")[-1] if "." in filename else "txt"
        if f".{file_ext}" not in ALLOWED_EXTENSIONS:
            raise InvalidUpload(
                f"不支持的文件类型: {file_ext}，支持的类型: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        max_size_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(content) > max_size_bytes:
            raise InvalidUpload(f"文件大小超过限制: {MAX_UPLOAD_SIZE_MB}MB")

        doc_id = new_id()
        file_name = f"{doc_id}.{file_ext}"
        save_dir = UPLOADS_DIR / doc_id
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / file_name).write_bytes(content)

        # storage_key: 相对于 DATA_DIR 的路径
        storage_key = f"documents/uploads/{doc_id}/{file_name}"

        doc = self.doc_repo.create(
            doc_id=doc_id,
            user_id=user_id,
            title=filename,
            source="uploaded",
            file_name=file_name,
            storage_key=storage_key,
            file_type=file_ext,
            file_size=len(content),
            status="pending",
        )
        # 短连接模式下 _execute 已自动 commit，无需手动提交

        background_tasks.add_task(_extract_background, user_id, doc.id)
        return doc

    # ── 重新提取 ─────────────────────────────────────────
    def trigger_extract(
        self, user_id: str, doc_id: str, background_tasks: BackgroundTasks
    ) -> dict:
        doc = self._assert_doc_owner(user_id, doc_id)
        background_tasks.add_task(_extract_background, doc.user_id, doc_id)
        return {"message": "提取任务已启动", "doc_id": doc_id}

    # ── 读取内容 ─────────────────────────────────────────
    def get_content(self, user_id: str, doc_id: str) -> dict[str, Any]:
        doc = self._assert_doc_owner(user_id, doc_id)
        if doc.status not in ["ready", "failed"]:
            raise DocumentNotReady(f"文档 {doc_id} 状态为 {doc.status}")

        file_path = Path(doc.get_file_path())
        if not file_path.exists():
            raise DocumentNotFound(f"文件不存在: {file_path}")

        extract_service = ExtractService()
        content, segments = extract_service.read_and_segment(
            str(file_path), doc.file_type
        )
        return {
            "content": content,
            "total_pages": doc.total_pages,
            "segments": segments,
        }

    # ── 下载 ─────────────────────────────────────────────
    def get_download_info(self, user_id: str, doc_id: str) -> tuple[Path, str]:
        doc = self._assert_doc_owner(user_id, doc_id)
        file_path = Path(doc.get_file_path())
        if not file_path.exists():
            raise DocumentNotFound(f"文件不存在: {file_path}")
        return file_path, doc.file_name

    # ── 删除 ─────────────────────────────────────────────
    def delete(self, user_id: str, doc_id: str) -> None:
        doc = self._assert_doc_owner(user_id, doc_id)
        # 只允许删除用户自己上传的文档，其他来源的文档不允许删除
        if doc.source != "uploaded":
            raise PermissionError(f"只能删除用户上传的文档，当前文档来源: {doc.source}")
        file_path = Path(doc.get_file_path())
        if file_path.exists():
            file_path.unlink(missing_ok=True)
        # 删除文档专属目录（仅当目录为空或只属于该文档时）
        if file_path.parent.exists() and file_path.parent != UPLOADS_DIR:
            shutil.rmtree(file_path.parent, ignore_errors=True)
        self.doc_repo.delete(doc_id)

    # ── 摘要 ─────────────────────────────────────────────
    def get_summary(self, user_id: str, doc_id: str) -> dict[str, Any]:
        doc = self._assert_doc_owner(user_id, doc_id)
        if doc.status != "ready":
            raise DocumentNotReady(f"文档 {doc_id} 状态为 {doc.status}")

        node_stats = {
            "total_nodes": len(doc.node_ids),
            "concept_nodes": 0,
            "example_nodes": 0,
            "other_nodes": 0,
        }
        for node_id in doc.node_ids:
            node = self.node_repo.get_by_id(node_id)
            if node:
                if node.content.examples:
                    node_stats["example_nodes"] += 1
                else:
                    node_stats["concept_nodes"] += 1

        try:
            extract_service = ExtractService()
            file_path = Path(doc.get_file_path())
            content = extract_service.read_content(str(file_path), doc.file_type)
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

    # ── 文档 ↔ 节点关联 ─────────────────────────────────
    def list_document_nodes(self, user_id: str, doc_id: str) -> dict[str, Any]:
        doc = self._assert_doc_owner(user_id, doc_id)

        nodes = []
        for node_id in doc.node_ids:
            node = self.node_repo.get_by_id(node_id)
            if not node:
                continue
            doc_origin = next(
                (
                    o
                    for o in node.origins
                    if o.source_type == "document" and o.source_id == doc_id
                ),
                None,
            )
            nodes.append(
                {
                    "node_id": node.id,
                    "title": node.title,
                    "description": node.description,
                    "origin": doc_origin.dict() if doc_origin else None,
                }
            )
        return {
            "document_id": doc_id,
            "document_title": doc.title,
            "nodes": nodes,
        }

    def list_node_documents(self, user_id: str, node_id: str) -> dict[str, Any]:
        node = self._assert_node_owner(user_id, node_id)

        documents = []
        for origin in node.origins:
            if origin.source_type != "document":
                continue
            doc = self.doc_repo.get_by_id(origin.source_id)
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
        return {
            "node_id": node_id,
            "node_title": node.title,
            "documents": documents,
        }

    def add_node(self, user_id: str, doc_id: str, node_id: str) -> dict[str, Any]:
        doc = self._assert_doc_owner(user_id, doc_id)
        node = self._assert_node_owner(user_id, node_id)
        if node_id in doc.node_ids:
            raise NodeAlreadyLinked(node_id)

        origin = NodeOrigin(
            source_type="document",
            source_id=doc_id,
            source_title=doc.title,
            source_description=f"来自文档: {doc.title}",
        )
        self.node_repo.update(node_id, NodeUpdate(origins=node.origins + [origin]))
        self.doc_repo.set_node_ids(doc_id, doc.node_ids + [node_id])
        # 短连接模式下 _execute 已自动 commit

        return {"message": "节点已成功添加到文档", "doc_id": doc_id, "node_id": node_id}


# ── 模块级后台任务（独立连接） ─────────────────────────────
async def _extract_background(user_id: str, doc_id: str) -> None:
    """后台任务：提取知识节点。ExtractService 内部按需获取短连接。"""
    logger.info("开始后台提取任务，文档ID: %s", doc_id)
    try:
        extract_service = ExtractService()
        logger.info("ExtractService 创建成功，开始提取文档 %s", doc_id)
        await extract_service.extract(user_id, doc_id)
        logger.info("文档 %s 提取任务完成", doc_id)
    except Exception as e:  # pylint: disable=broad-except
        logger.exception("异步文档提取失败: %s, 错误: %s", doc_id, e)
