"""
SessionRepository：会话数据访问层

消息存储在独立 JSON 文件（data/sessions/{id}.json），
此 repo 只管理会话元数据（SQLite）+ 消息文件读写。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from config import SESSIONS_DIR
from models.session import (
    SessionSchema,
    SessionDetail,
    MessageSchema,
    SessionCreate,
    SessionFile,
    CanvasBlock,
)
from utils.validators import ensure_session_id
from .base import BaseRepository, _loads, _dumps, new_id, utcnow_str

# 解析一次基目录，避免每次拼路径都做磁盘解析
_SESSIONS_DIR_RESOLVED = SESSIONS_DIR.resolve()


def _row_to_schema(row: dict) -> SessionSchema:
    return SessionSchema(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        topic=row.get("topic"),
        status=row["status"],
        node_ids_covered=_loads(row["node_ids_covered"], []),
        files=_loads(row["files"], []),
        message_count=row["message_count"],
        duration_minutes=row["duration_minutes"],
        created_at=row["created_at"],
        ended_at=row["ended_at"],
    )


class SessionRepository(BaseRepository):
    def get_all(self, user_id: str, limit: int = 20) -> list[SessionSchema]:
        rows = self._fetchall(
            "SELECT * FROM sessions WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit * 3),  # 预多取，下面再过滤掉空壳
        )
        result: list[SessionSchema] = []
        for r in rows:
            schema = _row_to_schema(r)
            ws_data = self._read_workspace(schema.id)
            workspace = ws_data.get("workspace", {}) or {}
            stage = ws_data.get("stage", "") or ""
            chapters_state = workspace.get("chapters", []) or []
            generated_chapters = sum(
                1 for c in chapters_state if c.get("status") == "ready"
            )
            planned_chapters = workspace.get("planned_chapters") or len(chapters_state)

            # 过滤"空壳"沉浸式会话：
            #   - 没有任何聊天消息
            #   - 没有任何文件
            #   - 没有任何已完成章节
            #   - stage 处于初始/规划/失败 阶段（说明额度不够、planner 失败等导致根本没产出）
            is_immersive = (schema.title or "").startswith("[AI课程]")
            if (
                is_immersive
                and schema.message_count == 0
                and not schema.files
                and generated_chapters == 0
                and stage in ("", "planning", "failed")
            ):
                continue

            # 把进度信息回填到 schema（前端展示 / 决定能否 resume）
            schema.stage = stage
            schema.workspace = {
                **workspace,
                "generated_chapters": generated_chapters,
                "planned_chapters": planned_chapters,
            }
            result.append(schema)
            if len(result) >= limit:
                break
        return result

    def get_by_id(self, session_id: str) -> Optional[SessionSchema]:
        row = self._fetchone("SELECT * FROM sessions WHERE id=?", (session_id,))
        return _row_to_schema(row) if row else None

    def get_detail(self, session_id: str) -> Optional[SessionDetail]:
        session = self.get_by_id(session_id)
        if not session:
            return None
        messages = self._read_messages(session_id)
        data = session.model_dump()
        data.update(self._read_workspace(session_id))
        return SessionDetail(**data, messages=messages)

    def create(self, user_id: str, data: SessionCreate) -> SessionSchema:
        session_id = new_id()
        now = utcnow_str()

        self._execute(
            """
            INSERT INTO sessions
              (id, user_id, title, topic, status, node_ids_covered,
               files, message_count, duration_minutes, created_at, ended_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                session_id,
                user_id,
                None,
                data.topic,
                "active",
                _dumps(data.node_ids),
                _dumps([]),
                0,
                0,
                now,
                None,
            ),
        )
        # 初始化空消息文件和 workspace 文件
        self._messages_path(session_id).write_text("[]", encoding="utf-8")
        self._workspace_path(session_id).write_text(
            json.dumps(self._default_workspace(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.get_by_id(session_id)

    def append_message(self, session_id: str, message: MessageSchema) -> None:
        """追加一条消息到消息文件，并更新 message_count"""
        messages = self._read_messages(session_id)
        messages.append(message.model_dump(mode="json"))

        self._messages_path(session_id).write_text(
            json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._execute(
            "UPDATE sessions SET message_count=? WHERE id=?",
            (len(messages), session_id),
        )

    def update_nodes_covered(self, session_id: str, node_ids: list[str]) -> None:
        self._execute(
            "UPDATE sessions SET node_ids_covered=? WHERE id=?",
            (_dumps(node_ids), session_id),
        )

    def append_session_file(self, session_id: str, file: SessionFile) -> None:
        """向会话的 files 列表追加一条文件记录；同 file_id 时更新，避免重复。"""
        row = self._fetchone("SELECT files FROM sessions WHERE id=?", (session_id,))
        if not row:
            return
        files: list[dict] = _loads(row["files"], [])
        item = file.model_dump(mode="json")
        replaced = False
        for i, existing in enumerate(files):
            if existing.get("file_id") == item.get("file_id"):
                files[i] = {**existing, **item}
                replaced = True
                break
        if not replaced:
            files.append(item)
        self._execute(
            "UPDATE sessions SET files=? WHERE id=?", (_dumps(files), session_id)
        )

    def add_duration(self, session_id: str, minutes: int) -> None:
        """累加会话时长（不改变 status）"""
        self._execute(
            "UPDATE sessions SET duration_minutes=duration_minutes+? WHERE id=?",
            (minutes, session_id),
        )

    def update_status(self, session_id: str, status: str) -> None:
        """更新会话状态（如 active / completed）"""
        self._execute(
            "UPDATE sessions SET status=? WHERE id=?",
            (status, session_id),
        )

    def set_title(self, session_id: str, title: str) -> None:
        self._execute("UPDATE sessions SET title=? WHERE id=?", (title, session_id))

    def complete(
        self,
        session_id: str,
        duration_minutes: int,
        node_ids: list[str],
        files: list[dict],
    ) -> None:
        """收尾会话：标记 completed，并写入 duration / node_ids_covered / files / ended_at。"""
        now = utcnow_str()
        row = self._fetchone("SELECT files FROM sessions WHERE id=?", (session_id,))
        existing_files: list[dict] = _loads(row["files"], []) if row else []
        merged_by_id = {f.get("file_id"): f for f in existing_files if f.get("file_id")}
        for f in files or []:
            fid = f.get("file_id")
            if fid:
                merged_by_id[fid] = {**merged_by_id.get(fid, {}), **f}
        merged_files = list(merged_by_id.values())
        self.update_workspace(
            session_id,
            stage="completed",
            next_actions=[],
            workspace={"completed_at": now},
        )
        self._execute(
            """
            UPDATE sessions
               SET status='completed',
                   duration_minutes=?,
                   node_ids_covered=?,
                   files=?,
                   ended_at=?
             WHERE id=?
            """,
            (
                duration_minutes,
                _dumps(node_ids),
                _dumps(merged_files),
                now,
                session_id,
            ),
        )

    @staticmethod
    def _default_workspace() -> dict:
        return {
            "mode": None,
            "stage": "",
            "canvas_blocks": [],
            "current_block_id": None,
            "next_actions": [],
            "workspace": {},
        }

    @staticmethod
    def _safe_session_file(session_id: str, suffix: str) -> Path:
        """安全地基于 ``session_id`` 拼出位于 ``SESSIONS_DIR`` 内的文件路径。

        防御链：
        1. ``ensure_session_id`` 限制 ``session_id`` 必须是 UUID（非法直接 400）
        2. ``resolve()`` 后比较父目录，确保最终路径不会越过 ``SESSIONS_DIR``
        """
        ensure_session_id(session_id)
        target = (_SESSIONS_DIR_RESOLVED / f"{session_id}{suffix}").resolve()
        if target.parent != _SESSIONS_DIR_RESOLVED:
            raise ValueError("非法 session_id：路径越界")
        return target

    @staticmethod
    def _messages_path(session_id: str) -> Path:
        """根据 session_id 直接构造消息文件的绝对路径"""
        return SessionRepository._safe_session_file(session_id, ".json")

    @staticmethod
    def _workspace_path(session_id: str) -> Path:
        """根据 session_id 构造沉浸式 workspace 文件路径。"""
        return SessionRepository._safe_session_file(session_id, ".workspace.json")

    def _read_workspace(self, session_id: str) -> dict:
        path = self._workspace_path(session_id)
        default = self._default_workspace()
        if not path.exists():
            return default
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {**default, **data}
        except (json.JSONDecodeError, OSError):
            return default

    def _write_workspace(self, session_id: str, workspace: dict) -> None:
        self._workspace_path(session_id).write_text(
            json.dumps(workspace, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def update_workspace(self, session_id: str, **patch) -> dict:
        """更新 workspace 顶层字段并返回最新 workspace。"""
        workspace = self._read_workspace(session_id)
        nested = patch.pop("workspace", None)
        for key, value in patch.items():
            if value is not None:
                workspace[key] = value
        if nested:
            workspace["workspace"] = {**workspace.get("workspace", {}), **nested}
        self._write_workspace(session_id, workspace)
        return workspace

    def upsert_canvas_block(
        self,
        session_id: str,
        block: CanvasBlock | dict,
        *,
        current: bool = False,
        next_actions: Optional[list[dict]] = None,
        stage: Optional[str] = None,
        workspace_patch: Optional[dict] = None,
    ) -> dict:
        """新增或更新 LearningCanvas block，立即持久化，支持部分生成恢复。"""
        workspace = self._read_workspace(session_id)
        item = (
            block.model_dump(mode="json") if isinstance(block, CanvasBlock) else block
        )
        blocks: list[dict] = workspace.get("canvas_blocks", []) or []
        replaced = False
        for i, existing in enumerate(blocks):
            if existing.get("id") == item.get("id"):
                blocks[i] = {**existing, **item}
                replaced = True
                break
        if not replaced:
            blocks.append(item)
        workspace["canvas_blocks"] = blocks
        if current:
            workspace["current_block_id"] = item.get("id")
        if next_actions is not None:
            workspace["next_actions"] = next_actions
        if stage:
            workspace["stage"] = stage
        if workspace_patch:
            workspace["workspace"] = {
                **workspace.get("workspace", {}),
                **workspace_patch,
            }
        self._write_workspace(session_id, workspace)
        return workspace

    def _read_messages(self, session_id: str) -> list[dict]:
        path = self._messages_path(session_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
