"""沉浸式学习 - 用户主动完成确认。

生成流程结束后 session 状态为 active + stage=ready，
只有用户主动调用 complete_immersive_session 才标记为 completed。
"""

from __future__ import annotations

import logging
from typing import Dict, Any

from repositories import SessionRepository, StudyLogRepository
from utils.log_safe import safe_log

logger = logging.getLogger(__name__)


def complete_immersive_session(
    session_id: str,
    user_id: str,
    *,
    feedback: str = "",
) -> Dict[str, Any]:
    """用户主动确认完成学习会话。

    与自动 finish_session 不同，此接口由前端按钮触发。
    仅当 session 处于 active 状态且 stage 为 ready/partial_ready/completed 时有效。

    Args:
        session_id: 会话 ID
        user_id: 用户 ID（权属校验）
        feedback: 可选用户反馈

    Returns:
        {"ok": True, "session_id": ..., "message": ...}

    Raises:
        ValueError: session 不存在、不属于该用户、或不符合完成条件
    """
    repo = SessionRepository()
    session = repo.get_by_id(session_id)

    if not session:
        raise ValueError("会话不存在")
    if session.user_id != user_id:
        raise ValueError("无权操作该会话")
    if session.status == "completed":
        return {
            "ok": True,
            "session_id": session_id,
            "message": "该会话已标记为完成",
        }
    if session.status != "active":
        raise ValueError(f"会话状态 {session.status} 不允许标记完成")

    # 读取 workspace 确保有内容
    ws = repo._read_workspace(session_id)
    stage = ws.get("stage", "")
    workspace_data = ws.get("workspace", {}) or {}
    generated = workspace_data.get("generated_chapters", 0)

    if generated == 0 and stage not in ("ready", "completed", "partial_ready"):
        raise ValueError("课程尚未开始生成，无法标记完成")

    # 使用前端上报的累积学习时长（由 recordDuration 维护），
    # 不再用 time.time() - created_at 估算（用户可能中途离开做别的事）
    duration = session.duration_minutes or 5  # 默认 5 分钟（至少学了一会儿）

    # 收集 node_ids
    node_ids = list(session.node_ids_covered) if session.node_ids_covered else []

    # 收集 files
    files = [
        f.model_dump(mode="json") if hasattr(f, "model_dump") else f
        for f in (session.files or [])
    ]

    # 标记完成
    repo.complete(
        session_id=session_id,
        duration_minutes=duration,
        node_ids=node_ids,
        files=files,
    )

    # 写入 study_log（如果 duration > 0）
    if duration > 0:
        try:
            StudyLogRepository().add_log(
                user_id=user_id,
                minutes=duration,
                session_id=session_id,
                node_ids=node_ids,
            )
        except Exception as e:
            logger.warning("写入 study_log 失败: %s", e)

    # 如果有 feedback，保存到 workspace
    if feedback:
        repo.update_workspace(
            session_id,
            workspace={"user_feedback": feedback, "completed_by_user": True},
        )

    # ── 画像汇总：课程完成时更新统一画像事实 ──────────────────
    try:
        _summarize_to_profile(session, user_id, feedback)
    except Exception as e:
        logger.warning("课程完成画像汇总失败: %s", e)
    logger.info(
        "用户确认完成学习：session=%s, duration=%d min, nodes=%d",
        safe_log(session_id),
        duration,
        len(node_ids),
    )

    return {
        "ok": True,
        "session_id": session_id,
        "message": f"学习完成！共学习 {duration} 分钟，涉及 {len(node_ids)} 个知识点。",
        "duration_minutes": duration,
        "node_count": len(node_ids),
    }


def _summarize_to_profile(session, user_id: str, feedback: str) -> None:
    """课程完成时，将学习主题写入统一画像事实。"""
    from repositories import ProfileFactRepository, ProfileOverviewRepository

    topic = (session.topic or session.title or "").replace("[AI课程]", "").strip()
    if not topic:
        return

    value = f"完成沉浸式课程「{topic}」"
    if feedback:
        value += f"，反馈：{feedback.strip()}"
    ProfileFactRepository().upsert_candidate(
        user_id,
        category="goal",
        key=f"completed_topic:{topic}",
        value=value,
        evidence_type="behavior",
        confidence=0.75,
        importance=0.7,
        source_ref="immersive_completion",
    )
    ProfileOverviewRepository().refresh_source_snapshot(user_id)

    logger.info("课程完成画像汇总: topic=%s", topic)
