"""
Node（知识节点）模型
"""

from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import Field
from .base import BaseSchema


# ---------- 子结构 ----------


class NodeContent(BaseSchema):
    """节点知识内容"""

    key_points: list[str] = Field(default_factory=list, description="核心要点")
    examples: list[str] = Field(default_factory=list, description="示例/代码")
    common_mistakes: list[str] = Field(default_factory=list, description="常见误区")
    summary: str = Field(default="", description="AI 详细总结（Markdown）")


class NodeOrigin(BaseSchema):
    """节点来源定位"""

    source_type: Literal["document", "session"]
    source_id: str
    source_title: Optional[str] = None  # 来源名称（会话 title/topic 或文档 title）
    location: str = Field(description="'第3页' / '消息 #12'")
    excerpt: str = Field(description="原文摘录，≤200字")
    page_number: Optional[int] = None


class NodeRelation(BaseSchema):
    """与其他节点的关系"""

    target_node_id: str
    relation_type: Literal["prerequisite", "related", "extends", "contrasts"]


class MemoryState(BaseSchema):
    """SM-2 记忆状态"""

    ease_factor: float = 2.5
    interval: int = 1
    repetitions: int = 0
    due_date: Optional[datetime] = None
    last_review_at: Optional[datetime] = None
    mastery_level: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------- 完整节点 ----------


class NodeSchema(BaseSchema):
    id: str
    user_id: str
    title: str
    description: str
    tags: list[str]
    content: NodeContent
    origins: list[NodeOrigin]
    relations: list[NodeRelation]
    memory: MemoryState
    created_at: datetime
    updated_at: datetime


# ---------- 图谱用的轻量视图 ----------


class NodeBrief(BaseSchema):
    """知识图谱列表/图谱视图用，不含 content 详情"""

    id: str
    title: str
    description: str
    tags: list[str]
    relations: list[NodeRelation]
    mastery_level: float
    due_date: Optional[datetime] = None
    last_review_at: Optional[datetime] = None
    repetitions: int = 0


# ---------- 创建 / 更新 ----------


class NodeCreate(BaseSchema):
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    content: NodeContent = Field(default_factory=NodeContent)
    origins: list[NodeOrigin] = Field(default_factory=list)


class NodeUpdate(BaseSchema):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    content: Optional[NodeContent] = None
    origins: Optional[list[NodeOrigin]] = None
    relations: Optional[list[NodeRelation]] = None


class NodeReviewResult(BaseSchema):
    """用户复习一个节点后提交的评分"""

    quality: int = Field(ge=0, le=5, description="SM-2 质量评分 0~5")
