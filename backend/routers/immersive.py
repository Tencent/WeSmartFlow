"""
沉浸式学习（AI主导学习）路由

提供：
  POST /api/immersive/generate   — SSE 流式生成课件（核心接口）
  GET  /api/immersive/files/*    — 静态文件服务（PDF/图片/音频）
  GET  /api/immersive/courses    — 列出已生成的课程
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from services.immersive import immersive_generate
from config import COURSES_DIR
from dependencies import get_current_user
from services.quota import QuotaExceededError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/immersive", tags=["immersive"])

# ── 请求模型 ─────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    topic: str
    user_profile: Optional[str] = ""


# ── 权属校验辅助 ─────────────────────────────────────────────────


def _assert_immersive_path_owner(user_id: str, file_path: str) -> None:
    """
    校验 user_id 是否拥有对沉浸式课件文件 file_path 的访问权。

    规则：
      - file_path 是相对于 COURSES_DIR 的路径，形如 `{slug}_{session_id}/...`
      - 从 sessions 表反查该 user 的 session_id，比对完整 session_id 是否匹配
      - 不匹配则抛 404（不暴露"不存在 vs 无权限"的差异）
    """
    parts = file_path.replace("\\", "/").strip("/").split("/")
    # 至少需要 {course_slug}/... 一级
    if len(parts) < 1:
        raise HTTPException(status_code=404, detail="文件不存在")

    course_slug = parts[0]
    if "_" not in course_slug:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 取最后一个 _ 后面的部分作为 session_id（UUID 格式，36 字符）
    sid_suffix = course_slug.rsplit("_", 1)[-1]
    if len(sid_suffix) != 36:
        raise HTTPException(status_code=404, detail="文件不存在")

    from database import get_db

    with get_db() as conn:
        cur = conn.execute(
            "SELECT 1 FROM sessions WHERE user_id = ? AND id = ? LIMIT 1",
            (user_id, sid_suffix),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="文件不存在")


# ── SSE 生成接口 ─────────────────────────────────────────────────


@router.post("/generate")
async def generate_immersive(
    req: GenerateRequest, request: Request, user_id: str = Depends(get_current_user)
):
    """SSE 流式生成沉浸式课件。"""
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic 不能为空")

    async def event_stream():
        try:
            async for event in immersive_generate(
                topic=req.topic.strip(),
                user_profile=req.user_profile or "",
                user_id=user_id,
            ):
                # 检查客户端是否断开
                if await request.is_disconnected():
                    logger.info("客户端断开，停止生成")
                    break
                yield event
        except QuotaExceededError as e:
            import json

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


# ── 文件服务 ─────────────────────────────────────────────────────


@router.api_route("/files/{file_path:path}", methods=["GET", "HEAD"])
async def serve_file(
    file_path: str,
    user_id: str = Depends(get_current_user),
):
    """
    提供沉浸式课件的静态文件（PDF/图片/音频/练习题/讲解稿等）。

    鉴权：要求 Authorization: Bearer <token>；
         前端通过 pdfjs httpHeaders 或 fetch→blob 的方式携带（见 frontend/src/api/base.js）。
    权属：路径必须位于 COURSES_DIR 下，且 course 所属 session 必须属于当前用户。
    """
    full_path = (COURSES_DIR / file_path).resolve()

    # 安全检查：不能访问 COURSES_DIR 之外的文件
    if not str(full_path).startswith(str(COURSES_DIR)):
        raise HTTPException(status_code=403, detail="路径不允许")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    # 权属校验：通过 course_slug 末尾的完整 session_id 反查归属
    _assert_immersive_path_owner(user_id, file_path)

    # 根据后缀推断 MIME type
    suffix = full_path.suffix.lower()
    media_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".md": "text/markdown; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".tex": "text/plain; charset=utf-8",
    }

    return FileResponse(
        path=full_path,
        media_type=media_types.get(suffix, "application/octet-stream"),
    )


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

    # 查该用户全部 session_id（沉浸式 session 也存在 sessions 表中，
    # 见 services/immersive/persistence.py::create_session）
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
        # course_slug 形如 "{slug}_{session_id}"，取最后一个 _ 后的部分为 session_id
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

        # 统计已完成章节数
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
