"""
Session（学习会话）& Message 模型
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import Field
from .base import BaseSchema


class MessageArtifacts(BaseSchema):
    """消息附带产物，驱动前端渲染"""

    files: list[str] = Field(
        default_factory=list, description="生成的文件相对路径列表（左侧追加文档卡片）"
    )
    new_nodes: list[str] = Field(
        default_factory=list, description="本条消息新建的节点 id（图谱角标 +N）"
    )
    node_refs: list[str] = Field(
        default_factory=list, description="本条消息引用的已有节点 id（消息内高亮）"
    )
    mastery_delta: dict[str, float] = Field(
        default_factory=dict, description="{node_id: delta} 本条消息引起的掌握度变化"
    )
    quiz_ids: list[str] = Field(
        default_factory=list, description="本条消息生成的测验题 id 列表（渲染答题组件）"
    )


class MessageSchema(BaseSchema):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    # assistant 消息附加字段
    tool_calls: Optional[list[Any]] = None
    artifacts: MessageArtifacts = Field(default_factory=MessageArtifacts)


class SessionFile(BaseSchema):
    """会话中生成的文件记录。

    ``file_type`` 与 ``documents.file_type`` 取值保持一致，
    例如 ``html_card`` / ``viz`` / ``chapter_pdf`` / ``chapter_audio`` / ``quiz`` 等。
    """

    file_id: str = Field(description="对应 documents 表的 id（uuid）")
    title: str = Field(default="", description="文件标题（展示用）")
    file_type: str = Field(
        default="upload", description="文件类型（与 documents.file_type 对齐）"
    )
    created_at: Optional[datetime] = Field(default=None)
    from_message_id: Optional[str] = Field(
        default=None, description="哪条消息触发生成的"
    )


class CanvasBlock(BaseSchema):
    """沉浸式学习主内容区可渲染块。"""

    id: str
    type: Literal[
        "outline",
        "md",
        "quiz_batch",
        "explanation",
        "knowledge_card",
        "pdf",
        "audio",
        "summary",
        "chapter_status",
    ]
    title: str = ""
    status: Literal["pending", "generating", "ready", "failed"] = "ready"
    chapter_id: Optional[int] = None
    data: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class SessionSchema(BaseSchema):
    id: str
    user_id: str
    title: Optional[str]
    topic: Optional[str] = Field(
        default=None, description="学习主题，有值时 Agent 在首轮预建骨架节点"
    )
    status: Literal["active", "ended", "completed"]
    mode: Optional[Literal["chat", "immersive"]] = Field(
        default=None, description="学习模式：普通对话或沉浸式学习"
    )
    stage: str = Field(
        default="", description="沉浸式学习阶段，如 planning/partial_ready/completed"
    )
    canvas_blocks: list[CanvasBlock] = Field(
        default_factory=list, description="LearningCanvas 主内容区块"
    )
    current_block_id: Optional[str] = Field(default=None, description="当前聚焦内容块")
    next_actions: list[dict[str, Any]] = Field(
        default_factory=list, description="前端可展示的下一步动作"
    )
    workspace: dict[str, Any] = Field(
        default_factory=dict, description="沉浸式学习工作区状态"
    )
    node_ids_covered: list[str] = Field(
        default_factory=list, description="本次会话涉及的所有节点"
    )
    files: list[SessionFile] = Field(
        default_factory=list, description="本次会话生成的文件列表"
    )
    message_count: int
    duration_minutes: int
    created_at: datetime
    ended_at: Optional[datetime]


class SessionDetail(SessionSchema):
    """带完整消息列表的会话详情"""

    messages: list[MessageSchema]


# ---------- 创建 / 操作 ----------


class SessionCreate(BaseSchema):
    topic: Optional[str] = Field(
        default=None, description="学习主题，有值时 Agent 首轮预建骨架节点"
    )
    node_ids: list[str] = Field(
        default_factory=list, description="关联的已有节点（可选）"
    )


class ChatMessage(BaseSchema):
    """前端发送的一条消息"""

    content: str
