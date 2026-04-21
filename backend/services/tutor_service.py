"""
TutorService：管理会话生命周期，将 HTTP 请求和 Agent 运行解耦

职责：
- 创建 / 恢复会话
- 调用 TutorAgent.stream_chat() 流式处理消息
- 将 Agent 回复持久化为 Message
- 更新 study_logs（学习时长统计）
- 会话结束时计算时长、汇总掌握度变化
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from pathlib import Path

from agents.base_agent import BaseAgent
from agents.base_context import AgentContextBuilder
from agent_core.skills.loader import SkillsLoader

from agents.tools.search_nodes import SearchNodesTool
from agents.tools.get_node import GetNodeTool
from agents.tools.update_mastery import UpdateMasteryTool
from agents.tools.update_node import UpdateNodeTool
from agents.tools.create_quiz import CreateQuizTool
from agents.tools.create_node import SessionCreateNodeTool
from agents.tools.generate_card import GenerateCardTool
from agent_core.agent.base import (
    AgentFinalEvent,
    AgentFinishReason,
    FileCreatedEvent,
    NodeCreatedEvent,
    MasteryUpdatedEvent,
)
from agent_core.tool.registry import ToolRegistry
from agent_core.tool.web import TavilySearch, ArxivSearch, WebFetch
from agent_core.tool.filesystem import ReadFileTool, ListDirTool
from agent_core.tool.decorator import tool
from agent_core.builtins import BUILTIN_SKILLS_DIR
from models.session import (
    SessionSchema,
    MessageSchema,
    MessageArtifacts,
    SessionCreate,
    SessionFile,
)
from repositories import SessionRepository, StudyLogRepository, NodeRepository
from services.llm_factory import get_llm

logger = logging.getLogger(__name__)

# agents 专属 skills 目录
_AGENTS_SKILLS_DIR = Path(__file__).parent.parent / "agents" / "prompts" / "skills"


@tool
def get_current_time() -> str:
    """获取当前的日期和时间（北京时间，CST，UTC+8）"""
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.strftime("%Y年%m月%d日 %H:%M:%S（北京时间，周%A）")


class TutorService:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.session_repo = SessionRepository(db)
        self.study_log_repo = StudyLogRepository(db)
        self.node_repo = NodeRepository(db)

    def create_session(self, user_id: str, data: SessionCreate) -> SessionSchema:
        return self.session_repo.create(user_id, data)

    def get_session(self, session_id: str) -> SessionSchema | None:
        return self.session_repo.get_by_id(session_id)

    async def stream_chat(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
    ):
        """
        流式处理一条用户消息，逐步 yield 进度事件。

        Yield 类型（可在前端按类型区分展示）：
        - AgentThinkEvent      — LLM 正在思考，content 为思考文本
        - AgentToolCallEvent   — 正在调用工具，tool_name / arguments
        - AgentToolResultEvent — 工具执行完毕，result 为结果摘要
        - AgentFinalEvent      — 最终回复，content 为完整回复文本

        最终回复产出后，本方法会完成持久化（消息、掌握度、学习日志）。
        """
        session = self.session_repo.get_by_id(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")
        # AI课程（completed）允许继续对话（智流Agent），其他已结束会话拒绝
        is_immersive = (session.title or "").startswith("[AI课程]")
        if session.status != "active" and not is_immersive:
            raise ValueError("会话已结束")

        detail = self.session_repo.get_detail(session_id)
        chat_history = detail.messages if detail else []

        # 持久化用户消息
        user_msg = MessageSchema(
            id=str(uuid.uuid4()),
            role="user",
            content=user_message,
            created_at=datetime.now(timezone.utc),
        )
        self.session_repo.append_message(session_id, user_msg)

        mastery_changes: dict[str, float] = {}
        generated_file_ids: list[str] = []  # 仅路径，写入 MessageArtifacts.files
        generated_files_meta: list[
            dict
        ] = []  # {file_id, title}，写入 SessionSchema.files
        created_node_ids: list[str] = []
        created_quiz_ids: list[str] = []

        # 用队列桥接同步 hook 和异步生成器
        # hook 在工具执行完毕后同步触发，把业务事件 put_nowait 进队列
        # 生成器在每个 Agent 事件之后把队列里积压的事件一并 yield 出去
        _event_queue: asyncio.Queue = asyncio.Queue()

        def _tool_result_hook(
            tool_name: str, params: Dict[str, Any], result: Any
        ) -> None:
            """统一的工具结果 hook，实时收集各工具产生的副作用并推入事件队列。"""
            if tool_name == "generate_card":
                if isinstance(result, str) and not result.startswith("Error"):
                    generated_file_ids.append(result)
                    # params 里有 title，一并存下来供后续写 SessionFile 用
                    generated_files_meta.append(
                        {
                            "file_id": result,
                            "title": params.get("title", ""),
                        }
                    )
                    _event_queue.put_nowait(FileCreatedEvent(file_id=result))

            elif tool_name == "create_node":
                try:
                    data = json.loads(result) if isinstance(result, str) else result
                    if data.get("created"):
                        created_node_ids.append(data["node_id"])
                        _event_queue.put_nowait(
                            NodeCreatedEvent(
                                node_id=data["node_id"], title=data.get("title", "")
                            )
                        )
                except (json.JSONDecodeError, AttributeError):
                    pass

            elif tool_name == "create_quiz":
                try:
                    data = json.loads(result) if isinstance(result, str) else result
                    if "quiz_id" in data:
                        created_quiz_ids.append(data["quiz_id"])
                except (json.JSONDecodeError, AttributeError):
                    pass

            elif tool_name == "update_mastery":
                node_id = params.get("node_id")
                delta = params.get("delta", 0.0)
                if node_id and not (
                    isinstance(result, str) and result.startswith("Error")
                ):
                    mastery_changes[node_id] = mastery_changes.get(node_id, 0.0) + delta
                    _event_queue.put_nowait(
                        MasteryUpdatedEvent(node_id=node_id, delta=delta)
                    )

        def _flush_queue():
            """把队列里所有待发送的业务事件取出，作为列表返回。"""
            events = []
            while not _event_queue.empty():
                events.append(_event_queue.get_nowait())
            return events

        # 判断是否为 AI 主导学习（immersive）的 session
        is_immersive = (session.title or "").startswith("[AI课程]")

        tools = [
            get_current_time,
            SearchNodesTool(self.db, user_id),
            GetNodeTool(self.db, user_id),
            SessionCreateNodeTool(
                self.db, user_id, session_id, on_result_hook=_tool_result_hook
            ),
            UpdateNodeTool(self.db, user_id),
            UpdateMasteryTool(self.db, user_id, on_result_hook=_tool_result_hook),
            CreateQuizTool(
                self.db, user_id, session_id, on_result_hook=_tool_result_hook
            ),
        ]
        # AI 主导学习不需要卡片生成（课程 PDF 由 immersive_service 管理）
        if not is_immersive:
            tools.append(
                GenerateCardTool(
                    db=self.db,
                    user_id=user_id,
                    session_id=session_id,
                    on_result_hook=_tool_result_hook,
                )
            )
        tools.extend(
            [
                # 内置网络工具
                TavilySearch(),
                ArxivSearch(),
                WebFetch(),
                # 文件系统工具（限 skills 目录，供 Agent 动态加载 SKILL.md）
                ReadFileTool(
                    allowed_dir=BUILTIN_SKILLS_DIR,
                    extra_allowed_dirs=[_AGENTS_SKILLS_DIR],
                ),
                ListDirTool(
                    allowed_dir=BUILTIN_SKILLS_DIR,
                    extra_allowed_dirs=[_AGENTS_SKILLS_DIR],
                ),
            ]
        )
        registry = ToolRegistry(tools)
        context_builder = AgentContextBuilder(
            prompt_file=Path(__file__).parent.parent
            / "agents"
            / "prompts"
            / "tutor.md",
            skills_loader=SkillsLoader(workspace_skills_dir=_AGENTS_SKILLS_DIR),
        )
        agent = BaseAgent(
            llm=get_llm(), context_builder=context_builder, tool_registry=registry
        )

        final_content = ""
        try:
            async for event in agent.stream_chat(
                user_message, chat_history=chat_history
            ):
                # 先把 hook 积压的业务事件全部 yield 出去
                for biz_event in _flush_queue():
                    yield biz_event

                yield event

                if isinstance(event, AgentFinalEvent):
                    final_content = event.content

            # 生成器结束后再 flush 一次，防止最后一个工具的事件未被消费
            for biz_event in _flush_queue():
                yield biz_event

        except asyncio.CancelledError:
            # 被外部 task.cancel() 取消（用户点击停止），静默退出
            return
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("TutorAgent stream_chat 失败")
            final_content = f"抱歉，处理您的消息时遇到了问题：{e}"
            yield AgentFinalEvent(
                content=final_content,
                finish_reason=AgentFinishReason.ERROR,
            )

        # 持久化 assistant 消息
        # new_nodes：本轮新建的节点；node_refs：掌握度有变化的已有节点（排除新建的）
        new_nodes = created_node_ids
        node_refs = list(set(mastery_changes.keys()) - set(created_node_ids))
        all_node_ids = list(set(new_nodes + node_refs))

        now = datetime.now(timezone.utc)
        assistant_msg_id = str(uuid.uuid4())
        assistant_msg = MessageSchema(
            id=assistant_msg_id,
            role="assistant",
            content=final_content,
            created_at=now,
            artifacts=MessageArtifacts(
                files=generated_file_ids,
                new_nodes=new_nodes,
                node_refs=node_refs,
                mastery_delta=mastery_changes,
                quiz_ids=created_quiz_ids,
            ),
        )
        self.session_repo.append_message(session_id, assistant_msg)

        # 更新会话涉及的节点列表
        if all_node_ids:
            existing = session.node_ids_covered
            merged = list(set(existing + all_node_ids))
            self.session_repo.update_nodes_covered(session_id, merged)

        # 将本轮生成的文件追加到 SessionSchema.files，供再次打开会话时渲染
        # 注意：AI 主导学习（immersive）的 session files 是课程章节 PDF，不应追加卡片
        is_immersive = (session.title or "").startswith("[AI课程]")
        if not is_immersive:
            for meta in generated_files_meta:
                self.session_repo.append_session_file(
                    session_id,
                    SessionFile(
                        file_id=meta["file_id"],
                        title=meta["title"],
                        file_type="pdf",
                        created_at=now,
                        from_message_id=assistant_msg_id,
                    ),
                )

    def record_duration(self, user_id: str, session_id: str, minutes: int) -> None:
        """前端离开会话页面时调用，记录本次会话的学习时长"""
        session = self.session_repo.get_by_id(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")
        minutes = max(1, minutes)
        # 累加到 sessions.duration_minutes（不改变 status）
        self.session_repo.add_duration(session_id, minutes)
        # 同步更新今日学习日志
        all_node_ids = session.node_ids_covered or []
        self.study_log_repo.upsert_today(user_id, minutes, session_id, all_node_ids)
