"""沉浸式学习的数据库持久化层。

集中处理 sessions / study_logs / documents 三张表的写入。
运行在后台线程上（`asyncio.to_thread`），因此需自管
数据库连接（`with get_db()`），但具体表访问委托给 repositories。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

from models.session import SessionCreate, SessionFile
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
    repo.update_workspace(
        session.id,
        mode="immersive",
        stage="planning",
        next_actions=[],
        workspace={
            "topic": topic,
            "planned_chapters": 0,
            "generated_chapters": 0,
            "current_chapter_id": None,
            "chapters": [],
        },
    )
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
    """将每章 PDF 登记到 documents 表，供文档管理页面展示。

    幂等：
    - 若同一 (session_id, storage_key) 尚未登记，则插入新记录
    - 若已登记（说明此前已通过 register_single_chapter_document 落库），
      则只更新 node_ids 字段，回填知识节点关联
    """
    registered = 0
    backfilled = 0
    doc_repo = DocumentRepository()
    for ch in chapter_results:
        if not ch.get("pdf_exists") or not ch.get("pdf_path"):
            continue
        pdf_path = ch.get("pdf_path", "")
        abs_path = COURSES_DIR / pdf_path
        try:
            storage_key = str(abs_path.relative_to(DATA_DIR))
        except ValueError:
            storage_key = f"documents/courses/{pdf_path}"

        if doc_repo.exists_by_session_and_key(session_id, storage_key):
            # 已登记：回填 node_ids
            try:
                doc_repo.update_node_ids_by_session_and_key(
                    session_id, storage_key, node_ids[:15]
                )
                backfilled += 1
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("回填节点关联失败 ch=%s: %s", ch.get("chapter_id"), exc)
            continue

        if register_single_chapter_document(
            session_id=session_id,
            topic=topic,
            chapter=ch,
            node_ids=node_ids,
            user_id=user_id,
        ):
            registered += 1

    logger.info(
        "AI课程文档登记完成：新增 %d 个，回填节点 %d 个 → documents 表",
        registered,
        backfilled,
    )


def register_single_chapter_document(
    session_id: str,
    topic: str,
    chapter: Dict,
    node_ids: List[str],
    user_id: str,
) -> bool:
    """登记单一章节的 PDF 到 documents 表。

    供"每章生成完毕"立即落库使用，确保即使后续章节失败/中断，
    已完成章节也会出现在文档管理页面。

    Returns:
        True - 已登记一条新记录；False - 跳过（PDF 不存在 / 已登记过）。
    """
    if not chapter.get("pdf_exists"):
        return False
    pdf_path = chapter.get("pdf_path", "")
    if not pdf_path:
        return False

    abs_path = COURSES_DIR / pdf_path
    file_size = abs_path.stat().st_size if abs_path.exists() else 0
    num_pages = chapter.get("num_frames", 0)

    pdf_file_name = (
        Path(pdf_path).name
        if pdf_path
        else f"chapter_{chapter.get('chapter_id', '0')}.pdf"
    )

    # storage_key: 相对于 DATA_DIR 的路径
    try:
        storage_key = str(abs_path.relative_to(DATA_DIR))
    except ValueError:
        storage_key = f"documents/courses/{pdf_path}"

    doc_repo = DocumentRepository()

    # 幂等检查：同一 session + 同一 storage_key 不重复登记
    if doc_repo.exists_by_session_and_key(session_id, storage_key):
        logger.info(
            "AI课程文档已登记，跳过：session=%s storage_key=%s",
            session_id,
            storage_key,
        )
        return False

    doc_id = new_id()
    doc_repo.create_generated(
        doc_id=doc_id,
        user_id=user_id,
        title=f"[AI课程] {topic} — 第{chapter.get('chapter_id', '?')}章 {chapter.get('title', '')}",
        file_name=pdf_file_name,
        storage_key=storage_key,
        file_type="pdf",
        file_size=file_size,
        generation_prompt=f"AI主导学习课程: {topic}",
        session_id=session_id,
        node_ids=node_ids[:15] if node_ids else [],
    )
    if num_pages:
        doc_repo.set_pages(doc_id, num_pages)

    logger.info(
        "AI课程章节文档已登记：第%s章 → doc_id=%s",
        chapter.get("chapter_id", "?"),
        doc_id,
    )
    return True


def register_chapter_overview_md(
    session_id: str,
    topic: str,
    chapter_id: int,
    chapter_title: str,
    md_abs_path: Path,
    user_id: str,
    node_ids: List[str] | None = None,
) -> bool:
    """将章节核心要点 markdown 登记到 documents 表。

    与 PDF 平级的章节产物：让用户在文档管理里也能看到这份 .md。

    幂等：相同 (session_id, storage_key) 不重复登记。

    Returns:
        True - 新增一条记录；False - 跳过（文件不存在 / 已登记过）。
    """
    if not md_abs_path or not md_abs_path.exists():
        return False

    file_size = md_abs_path.stat().st_size
    if file_size == 0:
        return False

    try:
        storage_key = str(md_abs_path.relative_to(DATA_DIR))
    except ValueError:
        # 兜底：保留 documents/courses 风格相对前缀
        storage_key = f"documents/courses/{md_abs_path.name}"

    doc_repo = DocumentRepository()

    if doc_repo.exists_by_session_and_key(session_id, storage_key):
        return False

    doc_id = new_id()
    doc_repo.create_generated(
        doc_id=doc_id,
        user_id=user_id,
        title=f"[AI课程] {topic} — 第{chapter_id}章 {chapter_title} · 核心要点",
        file_name=md_abs_path.name,
        storage_key=storage_key,
        file_type="md",
        file_size=file_size,
        generation_prompt=f"AI主导学习课程: {topic}（章节核心要点）",
        session_id=session_id,
        node_ids=(node_ids or [])[:15],
    )
    logger.info(
        "AI课程章节核心要点 MD 已登记：第%s章 → doc_id=%s",
        chapter_id,
        doc_id,
    )
    return True


def update_workspace(session_id: str, **patch) -> dict:
    """更新沉浸式学习 workspace 顶层状态。"""
    return SessionRepository().update_workspace(session_id, **patch)


def upsert_canvas_block(
    session_id: str,
    block: dict,
    *,
    current: bool = False,
    next_actions: list[dict] | None = None,
    stage: str | None = None,
    workspace_patch: dict | None = None,
) -> dict:
    """新增或更新 LearningCanvas 内容块，立即持久化。"""
    return SessionRepository().upsert_canvas_block(
        session_id,
        block,
        current=current,
        next_actions=next_actions,
        stage=stage,
        workspace_patch=workspace_patch,
    )


def append_session_file(
    session_id: str,
    file_id: str,
    title: str,
    file_type: str = "pdf",
) -> None:
    """将已生成文件立即登记到 session.files，避免部分生成中断后丢失。"""
    SessionRepository().append_session_file(
        session_id,
        SessionFile(file_id=file_id, title=title, file_type=file_type),
    )


def cleanup_orphan_course_dirs() -> int:
    """清理 COURSES_DIR 下的孤儿课程目录。

    判定为孤儿的条件（任一满足即删）：
    1. 目录里没有 outline.json（说明 planner 都没跑通）
    2. 目录后缀的 session_id 在 sessions 表里查不到

    Returns:
        删除的目录数量。
    """
    import shutil

    if not COURSES_DIR.exists():
        return 0

    repo = SessionRepository()
    removed = 0
    for course_dir in COURSES_DIR.iterdir():
        if not course_dir.is_dir():
            continue

        name = course_dir.name
        outline_file = course_dir / "outline.json"

        # 提取 session_id：约定 slug 格式为 "<topic_slug>_<session_id>"
        # session_id 是 uuid，含 4 个 '-'
        session_id_guess = ""
        if "_" in name:
            tail = name.rsplit("_", 1)[-1]
            # 简单校验是否像 uuid
            if len(tail) >= 32 and tail.count("-") >= 4:
                session_id_guess = tail

        is_orphan = False
        reason = ""

        if not outline_file.exists():
            is_orphan = True
            reason = "缺少 outline.json"
        elif session_id_guess:
            try:
                session = repo.get_by_id(session_id_guess)
                if session is None:
                    is_orphan = True
                    reason = f"sessions 表中无对应记录 {session_id_guess}"
            except Exception:
                # 查询失败就保守地不删
                pass

        if is_orphan:
            try:
                shutil.rmtree(course_dir, ignore_errors=True)
                removed += 1
                logger.info("清理孤儿课程目录: %s（原因：%s）", name, reason)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("清理孤儿目录失败 %s: %s", name, exc)

    if removed:
        logger.info("孤儿课程目录清理完成：共清理 %d 个", removed)
    return removed
