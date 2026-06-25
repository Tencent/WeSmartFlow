"""
Document（文档）模型
"""

from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from .base import BaseSchema


# documents.file_type 取值（统一在此处枚举，便于全局对齐）
#   ─ 用户上传 ─
#     upload                      用户上传的原始文件（具体格式由 file_name 后缀决定）
#   ─ AI 生成（chat 工具） ─
#     html_card                   HTML 知识卡片（主资源 card.html，伴生 images/*.png 等）
#     viz                         交互式可视化（主资源 viz.js）
#     pdf_card                    PDF 知识卡片（主资源 card.pdf，伴生 card.tex / images/*）
#     md_note                     单文件 markdown 笔记
#   ─ AI 生成（沉浸式课程） ─
#     course_outline              课程大纲 outline.json
#     course_plan                 整体学习建议 plan.md
#     chapter_overview            章节预习手册 overview.md
#     chapter_pdf                 章节 PDF 讲义
#     chapter_exercises           章节习题 markdown
#     chapter_audio               章节音频包（主资源 audio/manifest.json，伴生 frame_xxx.wav）
#     chapter_notes               章节讲解稿 speaker_notes.json


class DocumentSchema(BaseSchema):
    id: str
    user_id: str
    title: str
    source: Literal["uploaded", "generated"]
    file_name: str  # 只保存文件名，不保存完整路径
    storage_key: str  # 相对于 DATA_DIR 的存储路径
    file_type: str
    file_size: int
    status: Literal["pending", "processing", "ready", "failed"]
    error_msg: Optional[str]
    total_pages: Optional[int]
    generated_from_session_id: Optional[str]
    # AI生成文档的元数据
    generation_prompt: Optional[str] = None  # 生成提示词
    node_ids: list[str]
    created_at: datetime
    processed_at: Optional[datetime]

    def get_file_path(self) -> str:
        """通过 storage_key 动态生成文件绝对路径"""
        from config import DATA_DIR

        return str(DATA_DIR / self.storage_key)


class DocumentBrief(BaseSchema):
    """列表页用的轻量视图"""

    id: str
    title: str
    source: Literal["uploaded", "generated"]
    file_type: str
    file_size: int
    status: str
    total_pages: Optional[int]
    node_ids: list[str]
    node_count: int
    created_at: datetime
