"""
DocumentRepository：文档数据访问层
"""

from __future__ import annotations
from typing import Optional
from models.document import DocumentSchema, DocumentBrief
from .base import BaseRepository, _loads, _dumps, utcnow_str


def _row_to_schema(row: dict) -> DocumentSchema:
    return DocumentSchema(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        source=row["source"],
        file_name=row["file_name"],
        storage_key=row["storage_key"],
        file_type=row["file_type"],
        file_size=row["file_size"],
        status=row["status"],
        error_msg=row["error_msg"],
        total_pages=row["total_pages"],
        generated_from_session_id=row["generated_from_session_id"],
        generation_prompt=row.get("generation_prompt"),
        node_ids=_loads(row["node_ids"], []),
        created_at=row["created_at"],
        processed_at=row["processed_at"],
    )


class DocumentRepository(BaseRepository):
    def get_all(self, user_id: str) -> list[DocumentBrief]:
        rows = self._fetchall(
            "SELECT * FROM documents WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        )
        return [
            DocumentBrief(
                id=r["id"],
                title=r["title"],
                source=r["source"],
                file_type=r["file_type"],
                file_size=r["file_size"],
                status=r["status"],
                total_pages=r["total_pages"],
                node_ids=_loads(r["node_ids"], []),
                node_count=len(_loads(r["node_ids"], [])),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_by_id(self, doc_id: str) -> Optional[DocumentSchema]:
        row = self._fetchone("SELECT * FROM documents WHERE id=?", (doc_id,))
        return _row_to_schema(row) if row else None

    def create(
        self,
        doc_id: str,
        user_id: str,
        title: str,
        source: str,
        file_name: str,
        storage_key: str,
        file_type: str,
        file_size: int,
        generated_from_session_id: str = None,
        generation_prompt: str = None,
    ) -> DocumentSchema:
        now = utcnow_str()
        self._execute(
            """
            INSERT INTO documents
              (id, user_id, title, source, file_name, storage_key, file_type, file_size,
               status, generated_from_session_id, generation_prompt, node_ids, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                doc_id,
                user_id,
                title,
                source,
                file_name,
                storage_key,
                file_type,
                file_size,
                "pending",
                generated_from_session_id,
                generation_prompt,
                "[]",
                now,
            ),
        )
        # 不在这里commit，让调用方控制事务
        # 直接返回构建的文档对象，避免再次查询
        return DocumentSchema(
            id=doc_id,
            user_id=user_id,
            title=title,
            source=source,
            file_name=file_name,
            storage_key=storage_key,
            file_type=file_type,
            file_size=file_size,
            status="pending",
            error_msg=None,
            total_pages=None,
            generated_from_session_id=generated_from_session_id,
            generation_prompt=generation_prompt,
            node_ids=[],
            created_at=now,
            processed_at=None,
        )

    def create_generated(
        self,
        doc_id: str,
        user_id: str,
        title: str,
        file_name: str,
        storage_key: str,
        file_type: str,
        file_size: int,
        generation_prompt: str,
        session_id: str = None,
        node_ids: list = None,
    ) -> DocumentSchema:
        """创建AI生成的文档"""
        now = utcnow_str()
        node_ids_json = _dumps(node_ids or [])

        self._execute(
            """
            INSERT INTO documents
              (id, user_id, title, source, file_name, storage_key, file_type, file_size,
               status, generated_from_session_id, generation_prompt, node_ids, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                doc_id,
                user_id,
                title,
                "generated",
                file_name,
                storage_key,
                file_type,
                file_size,
                "ready",
                session_id,
                generation_prompt,
                node_ids_json,
                now,
            ),
        )
        # 不在这里commit，让调用方控制事务

        return DocumentSchema(
            id=doc_id,
            user_id=user_id,
            title=title,
            source="generated",
            file_name=file_name,
            storage_key=storage_key,
            file_type=file_type,
            file_size=file_size,
            status="ready",
            error_msg=None,
            total_pages=None,
            generated_from_session_id=session_id,
            generation_prompt=generation_prompt,
            node_ids=node_ids or [],
            created_at=now,
            processed_at=now,
        )

    def set_status(self, doc_id: str, status: str, error_msg: str = None) -> None:
        now = utcnow_str()
        if status == "ready":
            self._execute(
                "UPDATE documents SET status=?, processed_at=?, error_msg=? WHERE id=?",
                (status, now, error_msg, doc_id),
            )
        else:
            self._execute(
                "UPDATE documents SET status=?, error_msg=? WHERE id=?",
                (status, error_msg, doc_id),
            )
        # 不在这里commit，让调用方控制事务

    def set_node_ids(self, doc_id: str, node_ids: list[str]) -> None:
        self._execute(
            "UPDATE documents SET node_ids=? WHERE id=?", (_dumps(node_ids), doc_id)
        )
        # 不在这里commit，让调用方控制事务

    def set_pages(self, doc_id: str, total_pages: int) -> None:
        self._execute(
            "UPDATE documents SET total_pages=? WHERE id=?", (total_pages, doc_id)
        )
        # 不在这里commit，让调用方控制事务

    def exists_by_session_and_key(self, session_id: str, storage_key: str) -> bool:
        """判断同一会话下指定 storage_key 的文档是否已登记，用于幂等保护。"""
        row = self._fetchone(
            "SELECT id FROM documents WHERE generated_from_session_id=? AND storage_key=? LIMIT 1",
            (session_id, storage_key),
        )
        return row is not None

    def update_node_ids_by_session_and_key(
        self, session_id: str, storage_key: str, node_ids: list[str]
    ) -> None:
        """按 (session_id, storage_key) 回填节点关联，用于章节生成完成后补齐节点信息。"""
        self._execute(
            "UPDATE documents SET node_ids=? WHERE generated_from_session_id=? AND storage_key=?",
            (_dumps(node_ids or []), session_id, storage_key),
        )

    def delete(self, doc_id: str) -> bool:
        cursor = self._execute("DELETE FROM documents WHERE id=?", (doc_id,))
        # 不在这里commit，让调用方控制事务
        return cursor.rowcount > 0
