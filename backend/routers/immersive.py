"""
沉浸式学习（AI主导学习）路由

提供：
  POST /api/immersive/generate            — SSE 流式生成课件（核心接口）
  POST /api/immersive/resume              — 断点续传（恢复生成）
  GET  /api/immersive/exercises/:sid/:cid  — 获取结构化习题数据
  POST /api/immersive/quiz-result          — 上报答题结果
  POST /api/immersive/complete             — 用户确认完成学习
  GET  /api/immersive/courses             — 列出已生成的课程
  GET  /api/immersive/suggestions         — 个性化推荐云朵

文件读取统一走 ``/api/documents/{doc_id}/raw|asset/{sub}`` 接口，
本路由不再提供静态文件服务。
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.immersive import (
    immersive_generate,
    immersive_resume,
    get_exercises_for_chapter,
    complete_immersive_session,
)
from config import COURSES_DIR
from dependencies import get_current_user
from services.quota import QuotaExceededError
from services.content_guard import get_content_guard
from utils.validators import SessionIdField, SessionIdPath, sanitize_uuid
from utils.log_safe import safe_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/immersive", tags=["immersive"])

# ── 请求模型 ─────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    topic: str
    user_profile: Optional[str] = ""
    enable_audio: bool = False
    enable_exercises: bool = True


# ── SSE 生成接口 ─────────────────────────────────────────────────


@router.post("/generate")
async def generate_immersive(
    req: GenerateRequest, request: Request, user_id: str = Depends(get_current_user)
):
    """SSE 流式生成沉浸式课件。"""
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic 不能为空")

    # ── 内容安全审核（输入） ──
    guard = get_content_guard()
    if guard.enabled:
        guard_result = await guard.check_input(req.topic.strip())
        if not guard_result.is_safe:
            guard.log_violation(user_id, req.topic, guard_result)
            raise HTTPException(
                status_code=400,
                detail=guard_result.reason,
            )

    async def event_stream():
        try:
            async for event in immersive_generate(
                topic=req.topic.strip(),
                user_profile=req.user_profile or "",
                user_id=user_id,
                enable_audio=req.enable_audio,
                enable_exercises=req.enable_exercises,
            ):
                # 检查客户端是否断开
                if await request.is_disconnected():
                    logger.info("客户端断开，停止生成")
                    break
                yield event
        except QuotaExceededError as e:
            err = json.dumps(
                {
                    "type": "error",
                    "message": str(e),
                    "code": "quota_exceeded",
                    "category": e.category,
                    "limit": e.limit,
                },
                ensure_ascii=False,
            )
            yield f"data: {err}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 断点续传 ───────────────────────────────────────────────────


class ResumeRequest(BaseModel):
    session_id: SessionIdField


@router.post("/resume")
async def resume_immersive(
    req: ResumeRequest, request: Request, user_id: str = Depends(get_current_user)
):
    """SSE 流式恢复生成（断点续传）。

    从中断处继续生成尚未完成的章节，复用已有大纲和 course_dir。
    """
    if not req.session_id.strip():
        raise HTTPException(status_code=400, detail="session_id 不能为空")

    # ── 入口显式净化（SAST sanitizer）──
    session_id = sanitize_uuid(req.session_id.strip(), field_name="session_id")

    async def event_stream():
        try:
            async for event in immersive_resume(
                session_id=session_id,
                user_id=user_id,
            ):
                if await request.is_disconnected():
                    logger.info("客户端断开，停止恢复生成")
                    break
                yield event
        except QuotaExceededError as e:
            err = json.dumps(
                {
                    "type": "error",
                    "message": str(e),
                    "code": "quota_exceeded",
                    "category": e.category,
                    "limit": e.limit,
                },
                ensure_ascii=False,
            )
            yield f"data: {err}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 习题 API ──────────────────────────────────────────────────


@router.get("/exercises/{session_id}/{chapter_id}")
async def get_exercises(
    session_id: SessionIdPath,
    chapter_id: int,
    limit: int = 0,
    user_id: str = Depends(get_current_user),
):
    """获取指定会话某章节的结构化习题数据。

    返回已解析的 JSON 题目列表，前端无需自行解析 Markdown。
    ?limit=N 可限制返回题目数量（默认 0 = 全部）。
    """
    # ── 入口显式净化（SAST sanitizer）──
    # 通过 uuid.UUID 解析 + str 重格式化，将外部输入替换为可信字符串，
    # 切断污点（taint）传播链，所有下游调用使用净化后的值。
    session_id = sanitize_uuid(session_id, field_name="session_id")

    try:
        result = get_exercises_for_chapter(
            session_id=session_id,
            chapter_id=chapter_id,
            user_id=user_id,
            limit=limit,
        )
        return result
    except ValueError as e:
        # 不向前端暴露异常详情；详细原因仅记到服务端日志
        logger.warning(
            "获取习题失败 user=%s session=%s chapter=%s: %s",
            safe_log(user_id),
            safe_log(session_id),
            safe_log(chapter_id),
            e,
        )
        raise HTTPException(status_code=404, detail="习题不存在或不可访问")


# ── 习题作答结果上报 ──────────────────────────────────────────


class QuizAnswerItem(BaseModel):
    question: str = ""
    user_answer: str = ""
    correct_answer: str = ""
    correct: bool = False
    difficulty: str = ""  # 简单 | 中等 | 困难


class QuizResultRequest(BaseModel):
    session_id: SessionIdField
    chapter_id: int
    chapter_title: str = ""
    results: list[QuizAnswerItem] = []


@router.post("/quiz-result")
async def submit_quiz_result(
    req: QuizResultRequest,
    user_id: str = Depends(get_current_user),
):
    """前端习题完成后批量上报答题结果，用于更新用户画像中的知识点掌握度。"""
    from services.immersive.profile_updater import update_profile_from_quiz

    if not req.results:
        return {"status": "ok", "message": "无答题数据"}

    # ── 入口显式净化（SAST sanitizer）──
    session_id = sanitize_uuid(req.session_id, field_name="session_id")

    try:
        result = await update_profile_from_quiz(
            user_id=user_id,
            session_id=session_id,
            chapter_id=req.chapter_id,
            chapter_title=req.chapter_title,
            results=[r.model_dump() for r in req.results],
        )
        return result
    except Exception:
        # 不向前端暴露异常详情；详细堆栈仅记到服务端日志
        logger.exception(
            "习题结果上报处理失败 user=%s session=%s chapter=%s",
            safe_log(user_id),
            safe_log(session_id),
            safe_log(req.chapter_id),
        )
        return {"status": "partial", "message": "处理失败，请稍后重试"}


# ── 用户确认完成 ──────────────────────────────────────────────


class CompleteRequest(BaseModel):
    session_id: SessionIdField
    feedback: Optional[str] = ""


@router.post("/complete")
async def complete_session(
    req: CompleteRequest,
    user_id: str = Depends(get_current_user),
):
    """用户主动确认完成学习会话。

    生成流程结束后 session 仍为 active，只有用户确认后才标记 completed。
    """
    # ── 入口显式净化（SAST sanitizer）──
    session_id = sanitize_uuid(req.session_id, field_name="session_id")

    try:
        result = complete_immersive_session(
            session_id=session_id,
            user_id=user_id,
            feedback=req.feedback or "",
        )
        return result
    except ValueError as e:
        # 不向前端暴露异常详情；详细原因仅记到服务端日志
        logger.warning(
            "确认完成会话失败 user=%s session=%s: %s",
            safe_log(user_id),
            safe_log(session_id),
            e,
        )
        raise HTTPException(status_code=400, detail="请求参数不合法或会话状态异常")


# ── 课程列表 ─────────────────────────────────────────────────────


@router.get("/courses")
async def list_courses(
    user_id: str = Depends(get_current_user),
):
    """列出当前用户已生成的沉浸式课程。

    目录结构：COURSES_DIR/{topic_slug}_{session_id}/...
    过滤策略：从 sessions 表反查该 user 的 session_id 集合，
    匹配 course_slug 末尾的完整 session_id。
    """
    courses_dir = COURSES_DIR
    if not courses_dir.exists():
        return {"courses": []}

    from database import get_db

    user_sids: set[str] = set()
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM sessions WHERE user_id = ?", (user_id,))
        for row in cur.fetchall():
            sid = row["id"]
            if sid:
                user_sids.add(sid)

    courses = []
    for d in sorted(courses_dir.iterdir()):
        if not d.is_dir():
            continue
        name = d.name
        if "_" not in name:
            continue
        sid_suffix = name.rsplit("_", 1)[-1]
        if sid_suffix not in user_sids:
            continue

        outline_file = d / "outline.json"
        outline = None
        if outline_file.exists():
            try:
                outline = json.loads(outline_file.read_text(encoding="utf-8"))
            except Exception:  # pylint: disable=broad-except
                pass

        chapter_dirs = sorted(
            [c for c in d.iterdir() if c.is_dir() and c.name.startswith("chapter_")]
        )
        chapters_with_pdf = sum(
            1
            for c in chapter_dirs
            if any(f.suffix == ".pdf" for f in c.iterdir() if f.is_file())
        )

        courses.append(
            {
                "slug": d.name,
                "topic": outline.get("topic", d.name) if outline else d.name,
                "overview": outline.get("overview", "") if outline else "",
                "total_chapters": len(outline.get("chapters", []))
                if outline
                else len(chapter_dirs),
                "completed_chapters": chapters_with_pdf,
                "path": str(d),
            }
        )

    return {"courses": courses}


# ── 个性化推荐云朵 ─────────────────────────────────────────────────


@router.get("/suggestions")
async def get_suggestions(
    user_id: str = Depends(get_current_user),
):
    """根据用户画像和学习历史，调用 LLM 生成个性化推荐主题云朵。"""
    from services.immersive.suggestions import generate_suggestions

    try:
        result = await generate_suggestions(user_id)
        return result
    except Exception as e:
        logger.warning("生成个性化推荐失败: %s", e)
        return {"suggestions": [], "source": "default"}
