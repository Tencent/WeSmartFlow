"""沉浸式学习的数据库持久化层。

职责：
  - 创建会话记录、收尾会话
  - 把章节产物（PDF/MD/习题/音频/讲解稿/大纲/学习建议）登记到 documents 表
  - 操作 sessions.canvas_blocks / files / workspace
  - 清理孤儿课程目录

每个 ``register_xxx`` 函数都满足同一契约：

  - 输入文件不存在或为空 → 返回 ``None``
  - 成功登记 → 返回 ``doc_id``
  - 主资源 ``storage_key`` 始终指向**前端可直接渲染的入口文件**

伴生文件（HTML 卡片图片、章节音频帧）不单独登记，
通过 ``GET /api/documents/{doc_id}/asset/{sub}`` 访问。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from models.session import SessionCreate, SessionFile
from repositories import (
    DocumentRepository,
    SessionRepository,
    StudyLogRepository,
)

from config import COURSES_DIR
from utils.log_safe import safe_log

logger = logging.getLogger(__name__)


# ── 会话生命周期 ────────────────────────────────────────────────


def create_session(topic: str, user_id: str) -> str:
    """创建一个 immersive 会话记录，返回 session_id。"""
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
    files: List[dict],
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


# ── 通用产物登记 helper ─────────────────────────────────────────


def _register_if_ready(
    *,
    path: Path,
    file_type: str,
    title: str,
    session_id: str,
    user_id: str,
    prompt: str = "",
    node_ids: Optional[List[str]] = None,
    total_pages: Optional[int] = None,
) -> Optional[str]:
    """统一登记入口：文件存在且非空才登记，返回 ``doc_id`` 或 ``None``。"""
    if not path or not path.exists() or path.stat().st_size == 0:
        return None
    doc = DocumentRepository().register_produced(
        user_id=user_id,
        title=title,
        file_path=path,
        file_type=file_type,
        session_id=session_id,
        generation_prompt=prompt,
        node_ids=(node_ids or [])[:15],
        total_pages=total_pages,
    )
    logger.info("已登记产物: file_type=%s doc_id=%s path=%s", file_type, doc.id, path)
    return doc.id


# ── 课程级产物 ───────────────────────────────────────────────────


def register_course_outline(
    *,
    session_id: str,
    topic: str,
    outline_path: Path,
    user_id: str,
) -> Optional[str]:
    """登记课程大纲 ``outline.json``。"""
    return _register_if_ready(
        path=outline_path,
        file_type="course_outline",
        title=f"[AI课程] {topic} · 大纲",
        session_id=session_id,
        user_id=user_id,
        prompt=f"AI主导学习课程: {topic}（大纲）",
    )


def register_course_plan(
    *,
    session_id: str,
    topic: str,
    plan_path: Path,
    user_id: str,
) -> Optional[str]:
    """登记整体学习建议 ``plan.md``。"""
    return _register_if_ready(
        path=plan_path,
        file_type="course_plan",
        title=f"[AI课程] {topic} · 个性化学习建议",
        session_id=session_id,
        user_id=user_id,
        prompt=f"AI主导学习课程: {topic}（学习建议）",
    )


# ── 章节级产物 ───────────────────────────────────────────────────


def register_chapter_overview(
    *,
    session_id: str,
    topic: str,
    chapter_id: int,
    chapter_title: str,
    md_path: Path,
    user_id: str,
    node_ids: Optional[List[str]] = None,
) -> Optional[str]:
    """登记一章预习手册 markdown。"""
    return _register_if_ready(
        path=md_path,
        file_type="chapter_overview",
        title=f"[AI课程] {topic} — 第{chapter_id}章 {chapter_title} · 预习手册",
        session_id=session_id,
        user_id=user_id,
        prompt=f"AI主导学习课程: {topic}（章节预习手册）",
        node_ids=node_ids,
    )


def register_chapter_pdf(
    *,
    session_id: str,
    topic: str,
    chapter_id: int,
    chapter_title: str,
    pdf_path: Path,
    num_pages: int,
    user_id: str,
    node_ids: Optional[List[str]] = None,
) -> Optional[str]:
    """登记一章 PDF 讲义。"""
    return _register_if_ready(
        path=pdf_path,
        file_type="chapter_pdf",
        title=f"[AI课程] {topic} — 第{chapter_id}章 {chapter_title}",
        session_id=session_id,
        user_id=user_id,
        prompt=f"AI主导学习课程: {topic}",
        node_ids=node_ids,
        total_pages=num_pages or None,
    )


def register_chapter_exercises(
    *,
    session_id: str,
    topic: str,
    chapter_id: int,
    chapter_title: str,
    exercises_path: Path,
    user_id: str,
    node_ids: Optional[List[str]] = None,
) -> Optional[str]:
    """登记一章习题 markdown。"""
    return _register_if_ready(
        path=exercises_path,
        file_type="chapter_exercises",
        title=f"[AI课程] {topic} — 第{chapter_id}章 {chapter_title} · 习题",
        session_id=session_id,
        user_id=user_id,
        prompt=f"AI主导学习课程: {topic}（章节习题）",
        node_ids=node_ids,
    )


def register_chapter_notes(
    *,
    session_id: str,
    topic: str,
    chapter_id: int,
    chapter_title: str,
    notes_path: Path,
    user_id: str,
) -> Optional[str]:
    """登记一章 ``speaker_notes.json`` 讲解稿。"""
    return _register_if_ready(
        path=notes_path,
        file_type="chapter_notes",
        title=f"[AI课程] {topic} — 第{chapter_id}章 {chapter_title} · 讲解稿",
        session_id=session_id,
        user_id=user_id,
        prompt=f"AI主导学习课程: {topic}（章节讲解稿）",
    )


def register_chapter_audio(
    *,
    session_id: str,
    topic: str,
    chapter_id: int,
    chapter_title: str,
    audio_dir: Path,
    audio_results: list[dict],
    speaker_notes: list[str],
    user_id: str,
) -> Optional[str]:
    """登记一章音频包到 documents（每章一条记录）。

    主资源是 ``audio/manifest.json``（包含每帧的 filename / duration / 文本），
    各 wav 帧通过 ``GET /api/documents/{doc_id}/asset/{filename}`` 访问。

    会自动写 ``manifest.json`` 到 ``audio_dir`` 下。
    """
    if not audio_dir or not audio_dir.exists():
        return None

    successful = [r for r in (audio_results or []) if r.get("success")]
    if not successful:
        return None

    frames = []
    for i, r in enumerate(successful):
        frames.append(
            {
                "index": i + 1,
                "filename": r.get("filename", f"frame_{i + 1:03d}.wav"),
                "duration_seconds": r.get("duration_seconds", 0),
                "text": speaker_notes[i] if i < len(speaker_notes) else "",
            }
        )

    manifest = {
        "chapter_id": chapter_id,
        "chapter_title": chapter_title,
        "frame_count": len(frames),
        "total_duration_seconds": sum(f["duration_seconds"] for f in frames),
        "frames": frames,
    }
    manifest_path = audio_dir / "manifest.json"
    try:
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("写入 audio manifest 失败 ch=%s: %s", chapter_id, exc)
        return None

    return _register_if_ready(
        path=manifest_path,
        file_type="chapter_audio",
        title=f"[AI课程] {topic} — 第{chapter_id}章 {chapter_title} · 音频",
        session_id=session_id,
        user_id=user_id,
        prompt=f"AI主导学习课程: {topic}（章节音频）",
    )


# ── workspace / canvas / files 操作 ─────────────────────────────


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
    file_type: str,
) -> None:
    """将已生成文件登记到 ``session.files``。

    ``file_id`` 必须是 ``documents.id``（uuid）。
    """
    SessionRepository().append_session_file(
        session_id,
        SessionFile(file_id=file_id, title=title, file_type=file_type),
    )


# ── 启动期清理 ──────────────────────────────────────────────────


def cleanup_orphan_course_dirs() -> int:
    """清理 ``COURSES_DIR`` 下的孤儿课程目录。

    判定为孤儿的条件（任一满足即删）：
      1. 目录里没有 ``outline.json``（说明 planner 都没跑通）
      2. 目录后缀的 ``session_id`` 在 sessions 表里查不到
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

        session_id_guess = ""
        if "_" in name:
            tail = name.rsplit("_", 1)[-1]
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
            except Exception as e:
                logger.warning(
                    "查询 sessions 表时出错，无法验证 session_id %s: %s",
                    safe_log(session_id_guess),
                    e,
                )

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
