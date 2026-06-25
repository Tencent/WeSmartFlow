"""
DocumentRepository：文档数据访问层

文档来源（source）只有两类：
  - "uploaded"  用户上传
  - "generated" AI 生成（chat 工具 / immersive 编排 等）

外部上传走 create()；AI 产物登记统一走 register_produced()。

钩子机制：
  ``register_produced`` 成功后会触发 ``on_register_produced(doc)`` 钩子，
  默认 no-op；backend 启动时会注入 KG 自动登记实现（services.kg_facade）。
  这样 repository 层不直接依赖 KG / facade，保持纯粹。
"""

from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional

from config import DATA_DIR
from models.document import DocumentSchema, DocumentBrief
from .base import BaseRepository, _loads, _dumps, new_id, utcnow_str


# ── 可注入钩子：register_produced 成功后回调（默认 no-op） ─────
# backend 启动时会被替换为 KG 自动登记实现（services.kg_facade）
def _noop_on_register_produced(_doc: DocumentSchema) -> None:
    """默认钩子，什么也不做。"""
    return None


on_register_produced: Callable[[DocumentSchema], None] = _noop_on_register_produced


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
    # ── 查询 ─────────────────────────────────────────
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

    # ── 统一写入入口 ─────────────────────────────────
    def create(
        self,
        *,
        doc_id: str,
        user_id: str,
        title: str,
        source: str,  # "uploaded" | "generated"
        file_name: str,
        storage_key: str,
        file_type: str,
        file_size: int,
        status: str = "pending",
        session_id: Optional[str] = None,
        generation_prompt: Optional[str] = None,
        node_ids: Optional[list[str]] = None,
        total_pages: Optional[int] = None,
    ) -> DocumentSchema:
        """统一写入入口，覆盖 uploaded / generated 两种来源。"""
        now = utcnow_str()
        node_ids = node_ids or []
        processed_at = now if status == "ready" else None

        self._execute(
            """
            INSERT INTO documents
              (id, user_id, title, source, file_name, storage_key, file_type, file_size,
               status, error_msg, total_pages, generated_from_session_id,
               generation_prompt, node_ids, created_at, processed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                status,
                None,
                total_pages,
                session_id,
                generation_prompt,
                _dumps(node_ids),
                now,
                processed_at,
            ),
        )
        return DocumentSchema(
            id=doc_id,
            user_id=user_id,
            title=title,
            source=source,
            file_name=file_name,
            storage_key=storage_key,
            file_type=file_type,
            file_size=file_size,
            status=status,
            error_msg=None,
            total_pages=total_pages,
            generated_from_session_id=session_id,
            generation_prompt=generation_prompt,
            node_ids=node_ids,
            created_at=now,
            processed_at=processed_at,
        )

    # ── 高阶产物登记 ─────────────────────────────────
    def register_produced(
        self,
        *,
        user_id: str,
        title: str,
        file_path: Path,
        file_type: str,
        doc_id: Optional[str] = None,
        session_id: Optional[str] = None,
        generation_prompt: str = "",
        node_ids: Optional[list[str]] = None,
        total_pages: Optional[int] = None,
    ) -> DocumentSchema:
        """登记一份"AI 已生成完毕"的产物到 documents 表。

        - file_path 必须是绝对路径，且必须落在 DATA_DIR 之下，
          会自动派生 storage_key（相对 DATA_DIR）和 file_name。
        - file_size 自动从磁盘获取，不存在时记为 0。
        - status 直接置为 ready。

        Args:
            doc_id: 显式指定主键（如卡片/Viz 已有自己的 id）；不传则随机分配。
        """
        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        # storage_key 必须是相对 DATA_DIR 的路径
        try:
            storage_key = str(file_path.resolve().relative_to(DATA_DIR.resolve()))
        except ValueError as exc:
            raise ValueError(
                f"register_produced: file_path 必须位于 DATA_DIR={DATA_DIR} 之下，"
                f"实际为 {file_path}"
            ) from exc

        file_size = file_path.stat().st_size if file_path.exists() else 0

        doc = self.create(
            doc_id=doc_id or new_id(),
            user_id=user_id,
            title=title,
            source="generated",
            file_name=file_path.name,
            storage_key=storage_key,
            file_type=file_type,
            file_size=file_size,
            status="ready",
            session_id=session_id,
            generation_prompt=generation_prompt,
            node_ids=node_ids or [],
            total_pages=total_pages,
        )

        # 触发钩子：用于联动 KG exhibit 登记等扩展逻辑
        # 钩子异常不影响主流程（document 已成功落库）
        try:
            on_register_produced(doc)
        except Exception:  # pylint: disable=broad-except
            import logging

            logging.getLogger(__name__).warning(
                "register_produced 钩子异常 doc_id=%s", doc.id, exc_info=True
            )

        return doc

    # ── 状态/字段更新 ────────────────────────────────
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

    def set_node_ids(self, doc_id: str, node_ids: list[str]) -> None:
        self._execute(
            "UPDATE documents SET node_ids=? WHERE id=?",
            (_dumps(node_ids), doc_id),
        )

    def set_pages(self, doc_id: str, total_pages: int) -> None:
        self._execute(
            "UPDATE documents SET total_pages=? WHERE id=?",
            (total_pages, doc_id),
        )

    def delete(self, doc_id: str) -> bool:
        cursor = self._execute("DELETE FROM documents WHERE id=?", (doc_id,))
        return cursor.rowcount > 0
