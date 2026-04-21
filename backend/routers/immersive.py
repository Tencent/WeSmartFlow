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

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from services.immersive_service import immersive_generate, IMMERSIVE_ROOT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/immersive", tags=["immersive"])


# ── 请求模型 ─────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    topic: str
    user_profile: Optional[str] = ""


# ── SSE 生成接口 ─────────────────────────────────────────────────


@router.post("/generate")
async def generate_immersive(req: GenerateRequest, request: Request):
    """SSE 流式生成沉浸式课件。"""
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic 不能为空")

    async def event_stream():
        async for event in immersive_generate(
            topic=req.topic.strip(),
            user_profile=req.user_profile or "",
        ):
            # 检查客户端是否断开
            if await request.is_disconnected():
                logger.info("客户端断开，停止生成")
                break
            yield event

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
async def serve_file(file_path: str):
    """
    提供沉浸式课件的静态文件（PDF/图片/音频/练习题/讲解稿等）。
    安全限制：路径必须在 IMMERSIVE_ROOT 下。
    """
    full_path = (IMMERSIVE_ROOT / file_path).resolve()

    # 安全检查：不能访问 IMMERSIVE_ROOT 之外的文件
    if not str(full_path).startswith(str(IMMERSIVE_ROOT)):
        raise HTTPException(status_code=403, detail="路径不允许")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

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
async def list_courses():
    """列出已生成的沉浸式课程。"""
    courses_dir = IMMERSIVE_ROOT / "courses"
    if not courses_dir.exists():
        return {"courses": []}

    courses = []
    for d in sorted(courses_dir.iterdir()):
        if d.is_dir():
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
