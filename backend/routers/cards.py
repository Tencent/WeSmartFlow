"""
卡片静态文件路由（带鉴权）

替代原先的 `app.mount("/files/cards", StaticFiles(...))`，
因为 StaticFiles 无法注入 FastAPI Depends，无法做鉴权。

资源命名约定（与 agents/tools/generate_card.py 对齐）：
  - PDF:        {card_id}/card.pdf
  - 音频目录:   {card_id}/audio/frame_{num}.wav
  - 讲解稿:     {card_id}/notes.json
  - LaTeX源:    {card_id}/card.tex

权属校验：取 file_path 第一段（按 '/' 切），
得到 card_id（即 documents.id），然后查 documents.user_id 是否匹配当前用户。
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from config import CARDS_DIR
from database import get_db
from dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files/cards", tags=["cards"])


def _extract_card_id(file_path: str) -> str | None:
    """
    从 file_path 推导 card_id（即 documents.id，通常是 uuid）。

    支持：
      "{card_id}/card.pdf"              → "{card_id}"
      "{card_id}/card.tex"              → "{card_id}"
      "{card_id}/audio/frame_001.wav"   → "{card_id}"
      "{card_id}/notes.json"            → "{card_id}"
    """
    first = file_path.replace("\\", "/").strip("/").split("/", 1)[0]
    return first or None


def _assert_card_owner(user_id: str, file_path: str) -> None:
    """校验 file_path 对应的 card 是否属于当前用户；不属于/不存在统一 404。"""
    card_id = _extract_card_id(file_path)
    if not card_id:
        raise HTTPException(status_code=404, detail="文件不存在")

    with get_db() as conn:
        cur = conn.execute(
            "SELECT user_id FROM documents WHERE id = ? LIMIT 1", (card_id,)
        )
        row = cur.fetchone()

    if row is None or row["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="文件不存在")


@router.api_route("/{file_path:path}", methods=["GET", "HEAD"])
async def serve_card_file(
    file_path: str,
    user_id: str = Depends(get_current_user),
):
    """提供生成的卡片静态文件（PDF/音频/讲解稿等），需鉴权 + 归属校验。"""
    full_path = (CARDS_DIR / file_path).resolve()

    # 防止路径穿越
    if not str(full_path).startswith(str(CARDS_DIR.resolve())):
        raise HTTPException(status_code=403, detail="路径不允许")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    _assert_card_owner(user_id, file_path)

    suffix = full_path.suffix.lower()
    media_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".json": "application/json; charset=utf-8",
        ".tex": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
    }
    return FileResponse(
        path=full_path,
        media_type=media_types.get(suffix, "application/octet-stream"),
    )
