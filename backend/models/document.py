"""
Document（文档）模型
"""

from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from .base import BaseSchema


class DocumentSchema(BaseSchema):
    id: str
    user_id: str
    title: str
    source: Literal["uploaded", "generated"]
    file_name: str  # 只保存文件名，不保存完整路径
    file_type: str
    file_size: int
    status: Literal["pending", "processing", "ready", "failed"]
    error_msg: Optional[str]
    total_pages: Optional[int]
    generated_from_session_id: Optional[str]
    # AI生成文档的元数据
    generation_prompt: Optional[str] = None  # 生成提示词
    generation_context: Optional[str] = None  # 生成上下文
    node_ids: list[str]
    created_at: datetime
    processed_at: Optional[datetime]

    def get_file_path(self) -> str:
        """动态生成文件存储路径"""
        from config import UPLOADS_DIR, CARDS_DIR
        import json as _json

        if self.source == "uploaded":
            return str(UPLOADS_DIR / self.id / self.file_name)

        # generated: 优先从 generation_context 中读取 immersive_pdf_path
        if self.generation_context:
            try:
                if isinstance(self.generation_context, str):
                    ctx = _json.loads(self.generation_context)
                else:
                    ctx = self.generation_context

                if isinstance(ctx, dict) and ctx.get("immersive_pdf_path"):
                    return ctx["immersive_pdf_path"]
            except (ValueError, TypeError):
                pass

        # fallback: cards 目录
        return str(CARDS_DIR / self.file_name)


class DocumentBrief(BaseSchema):
    """列表页用的轻量视图"""

    id: str
    title: str
    source: Literal["uploaded", "generated"]
    file_type: str
    file_size: int
    status: str
    total_pages: Optional[int]
    node_count: int
    created_at: datetime
