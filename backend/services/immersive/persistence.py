"""沉浸式学习的数据库持久化层。

集中处理 sessions / study_logs / documents 三张表的写入。
运行在后台线程上（`asyncio.to_thread`），因此需自管
数据库连接（`with get_db()`），但具体表访问委托给 repositories。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

from models.session import SessionCreate
from repositories import (
    SessionRepository,
    StudyLogRepository,
    DocumentRepository,
)
from repositories.base import new_id

from config import DATA_DIR, COURSES_DIR

logger = logging.getLogger(__name__)


def create_session(topic: str, user_id: str) -> str:
    """创建一个 immersive 会话记录，返回 session_id。

    immersive 场景需要自定义 title=`[AI课程] {topic}`，
    所以先 create 再 set_title。
    """
    repo = SessionRepository()
    session = repo.create(user_id, SessionCreate(topic=topic, node_ids=[]))
    repo.set_title(session.id, f"[AI课程] {topic}")
    return session.id


def finish_session(
    session_id: str,
    duration_minutes: int,
    node_ids: List[str],
    files: List[Dict],
    user_id: str,
) -> None:
    """收尾会话并写入 study_logs。"""
    SessionRepository().complete(
        session_id=session_id,
        duration_minutes=duration_minutes,
        node_ids=node_ids,
        files=files,
    )
    StudyLogRepository().add_log(
        user_id=user_id,
        minutes=duration_minutes,
        session_id=session_id,
        node_ids=node_ids,
    )


def register_chapter_documents(
    session_id: str,
    topic: str,
    chapter_results: List[Dict],
    node_ids: List[str],
    user_id: str,
) -> None:
    """将每章 PDF 登记到 documents 表，供文档管理页面展示。"""
    registered = 0
    doc_repo = DocumentRepository()
    for ch in chapter_results:
        if not ch.get("pdf_exists"):
            continue
        pdf_path = ch.get("pdf_path", "")
        if not pdf_path:
            continue

        abs_path = COURSES_DIR / pdf_path
        file_size = abs_path.stat().st_size if abs_path.exists() else 0
        num_pages = ch.get("num_frames", 0)

        doc_id = new_id()
        pdf_file_name = (
            Path(pdf_path).name
            if pdf_path
            else f"chapter_{ch.get('chapter_id', '0')}.pdf"
        )

        # storage_key: 相对于 DATA_DIR 的路径
        try:
            storage_key = str(abs_path.relative_to(DATA_DIR))
        except ValueError:
            storage_key = f"documents/courses/{pdf_path}"

        doc_repo.create_generated(
            doc_id=doc_id,
            user_id=user_id,
            title=f"[AI课程] {topic} — 第{ch.get('chapter_id', '?')}章 {ch.get('title', '')}",
            file_name=pdf_file_name,
            storage_key=storage_key,
            file_type="pdf",
            file_size=file_size,
            generation_prompt=f"AI主导学习课程: {topic}",
            session_id=session_id,
            node_ids=node_ids[:15],
        )
        # create_generated 不设置 total_pages，这里补上
        if num_pages:
            doc_repo.set_pages(doc_id, num_pages)
        registered += 1

    logger.info("AI课程文档登记完成：%d 个 PDF → documents 表", registered)
