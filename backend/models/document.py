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
