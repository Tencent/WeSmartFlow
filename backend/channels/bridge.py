"""weclaw ↔ edu-agent 大脑桥接。

收到微信消息后：
  1. 按 (owner_user_id, peer_id) 找/建一个 edu-agent 会话（每个微信对端独立上下文，
     但都归属 bot 的 owner，额度/画像算在 owner 头上）；
  2. 跑 ``TutorService.stream_chat`` 生成回复；
  3. 聚合成要发回微信的内容：正文文本 + 富产物（卡片/PDF）链接。

富产物无法在微信聊天气泡里原生渲染，统一降维为**链接**（微信 webview 打开）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agent_core.agent.events import AgentFinalEvent, DomainEvent
from agents.events import KIND_FILE_CREATED
from config import PUBLIC_BASE_URL
from models.session import SessionCreate
from repositories import SessionRepository
from services import TutorService
from services.content_guard import get_content_guard
from utils.file_ticket import create_file_ticket
from utils.log_safe import safe_log
from channels import store

logger = logging.getLogger(__name__)

# 微信里的链接会被反复点开，给 24 小时；但只能读这一个文档，且不是登录 token。
WECHAT_LINK_TICKET_MINUTES = 24 * 60


@dataclass
class BotReply:
    text: str = ""
    links: list[dict] = field(default_factory=list)  # [{title, url, kind}]
    # 可渲染成图片的卡片：[{doc_id, card_type, title, url}]
    cards: list[dict] = field(default_factory=list)

    def render_for_wechat(self) -> str:
        """把正文 + 链接拼成一段适合微信发送的纯文本。"""
        out = (self.text or "").strip()
        for link in self.links:
            title = link.get("title") or (
                "讲义 PDF" if link.get("kind") == "file" else "查看内容"
            )
            out += f"\n\n📎 {title}：{link.get('url', '')}"
        return out.strip() or "（暂时没有可返回的内容）"


def _build_asset_url(file_id: str, owner_user_id: str, *, download: bool) -> str:
    """生成发给微信的文档链接；只携带该文档的短时效票据，不含登录 token。"""
    base = PUBLIC_BASE_URL or ""
    ticket = create_file_ticket(
        owner_user_id, file_id, expires_in_minutes=WECHAT_LINK_TICKET_MINUTES
    )
    q = f"?ticket={ticket}" + ("&download=1" if download else "")
    return f"{base}/api/documents/{file_id}/raw{q}"


# 作为文件下发（链接）；其余卡片类渲染成图片
_RENDER_AS_FILE = {"pdf", "chapter_pdf"}
# 可渲染成图片的卡片类型
_RENDER_AS_IMAGE = {"html", "html_card", "viz", "viz_card", "quiz", "quiz_card"}


def _get_or_create_session(owner_user_id: str, peer_id: str) -> str:
    repo = SessionRepository()
    sid = store.get_peer_session(owner_user_id, peer_id)
    if sid and repo.get_by_id(sid) is not None:
        return sid
    session = repo.create(owner_user_id, SessionCreate(topic=None))
    try:
        repo.set_title(session.id, f"[微信助手] {peer_id}")
    except Exception:  # pylint: disable=broad-except
        pass
    store.set_peer_session(owner_user_id, peer_id, session.id)
    logger.info(
        "weclaw bridge: 为 owner=%s peer=%s 创建会话 %s",
        safe_log(owner_user_id),
        safe_log(peer_id),
        safe_log(session.id),
    )
    return session.id


async def generate_reply(owner_user_id: str, peer_id: str, text: str) -> BotReply:
    """驱动 edu-agent 对话大脑，聚合出要发回微信的回复。"""
    guard = get_content_guard()
    if guard.enabled:
        result = await guard.check_input(text)
        if not result.is_safe:
            guard.log_violation(owner_user_id, text, result)
            return BotReply(text=result.reason or "抱歉，该内容无法处理。")

    session_id = _get_or_create_session(owner_user_id, peer_id)
    service = TutorService()

    reply = BotReply()
    async for event in service.stream_chat(owner_user_id, session_id, text):
        if isinstance(event, DomainEvent) and event.kind == KIND_FILE_CREATED:
            file_id = event.payload.get("file_id", "")
            title = event.payload.get("title", "") or ""
            ft = (event.payload.get("file_type") or "").lower()
            if ft in _RENDER_AS_IMAGE:
                # 卡片类：渲染成图片发送，同时附带网页端交互链接
                reply.cards.append(
                    {
                        "doc_id": file_id,
                        "card_type": ft,
                        "title": title,
                        "url": _build_asset_url(file_id, owner_user_id, download=False),
                    }
                )
            else:
                as_file = ft in _RENDER_AS_FILE
                reply.links.append(
                    {
                        "title": title,
                        "url": _build_asset_url(
                            file_id, owner_user_id, download=as_file
                        ),
                        "kind": "file" if as_file else "link",
                    }
                )
        elif isinstance(event, AgentFinalEvent):
            reply.text = guard.sanitize_output(event.content)
    return reply
