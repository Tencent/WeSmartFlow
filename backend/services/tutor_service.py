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

import os
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from pathlib import Path

from agents import ChatAgent
from agent_core.context import SkillPromptContextBuilder
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
from services.quota import check_and_consume
from database import get_setting

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
    def __init__(self):
        self.session_repo = SessionRepository()
        self.study_log_repo = StudyLogRepository()
        self.node_repo = NodeRepository()

    # ── 权属校验 ──────────────────────────────────────
    def _assert_owner(self, user_id: str, session_id: str) -> SessionSchema | None:
        """断言会话存在且属于该用户；不存在或不属于该用户都返回 None
        （上层统一翻译为 404，避免通过状态码区分'不存在 vs 不属于你'）。"""
        session = self.session_repo.get_by_id(session_id)
        if not session or session.user_id != user_id:
            return None
        return session

    def create_session(self, user_id: str, data: SessionCreate) -> SessionSchema:
        return self.session_repo.create(user_id, data)

    def get_session(self, session_id: str) -> SessionSchema | None:
        return self.session_repo.get_by_id(session_id)

    def list_sessions(self, user_id: str) -> list[SessionSchema]:
        """列出用户的所有会话。"""
        return self.session_repo.get_all(user_id)

    def get_session_detail(self, user_id: str, session_id: str):
        """获取会话详情（含消息），仅限本人；不存在或不属于该用户都返回 None。"""
        if not self._assert_owner(user_id, session_id):
            return None
        return self.session_repo.get_detail(session_id)

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
        session = self._validate_session(user_id, session_id)
        is_immersive = (session.title or "").startswith("[AI课程]")

        detail = self.session_repo.get_detail(session_id)
        chat_history = detail.messages if detail else []

        # 持久化用户消息
        self.session_repo.append_message(
            session_id,
            MessageSchema(
                id=str(uuid.uuid4()),
                role="user",
                content=user_message,
                created_at=datetime.now(timezone.utc),
            ),
        )
        # 短连接模式下 _execute 已自动 commit，无需手动提交

        # 状态累加器（hook 与 stream 共享）
        state: Dict[str, Any] = {
            "mastery_changes": {},
            "generated_file_ids": [],
            "generated_files_meta": [],
            "created_node_ids": [],
            "created_quiz_ids": [],
        }
        event_queue: asyncio.Queue = asyncio.Queue()

        hook = self._make_result_hook(state, event_queue)
        registry = ToolRegistry(
            self._build_tools(user_id, session_id, hook, is_immersive)
        )
        agent = ChatAgent(
            llm=get_llm(user_id),
            context_builder=self._make_context_builder(),
            tool_registry=registry,
        )

        def _flush_queue() -> list:
            events = []
            while not event_queue.empty():
                events.append(event_queue.get_nowait())
            return events

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

        self._persist_assistant_message(
            session=session,
            final_content=final_content,
            state=state,
            is_immersive=is_immersive,
        )
        # 短连接模式下 _execute 已自动 commit，无需手动提交

    # ── stream_chat 的内部辅助方法 ────────────────────────

    def _validate_session(self, user_id: str, session_id: str) -> SessionSchema:
        """校验会话存在、属于本人、且处于可对话状态，返回 session 对象。"""
        session = self._assert_owner(user_id, session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")
        # AI课程（completed）允许继续对话（智流Agent），其他已结束会话拒绝
        is_immersive = (session.title or "").startswith("[AI课程]")
        if session.status != "active" and not is_immersive:
            raise ValueError("会话已结束")
        return session

    @staticmethod
    def _make_result_hook(state: Dict[str, Any], event_queue: asyncio.Queue):
        """构造工具结果 hook：收集副作用并向 event_queue 推入业务事件。"""

        def _hook(tool_name: str, params: Dict[str, Any], result: Any) -> None:
            if tool_name == "generate_card":
                if isinstance(result, str) and not result.startswith("Error"):
                    state["generated_file_ids"].append(result)
                    state["generated_files_meta"].append(
                        {"file_id": result, "title": params.get("title", "")}
                    )
                    event_queue.put_nowait(FileCreatedEvent(file_id=result))

            elif tool_name == "create_node":
                try:
                    data = json.loads(result) if isinstance(result, str) else result
                    if data.get("created"):
                        state["created_node_ids"].append(data["node_id"])
                        event_queue.put_nowait(
                            NodeCreatedEvent(
                                node_id=data["node_id"],
                                title=data.get("title", ""),
                            )
                        )
                except (json.JSONDecodeError, AttributeError):
                    pass

            elif tool_name == "create_quiz":
                try:
                    data = json.loads(result) if isinstance(result, str) else result
                    if "quiz_id" in data:
                        state["created_quiz_ids"].append(data["quiz_id"])
                except (json.JSONDecodeError, AttributeError):
                    pass

            elif tool_name == "update_mastery":
                node_id = params.get("node_id")
                delta = params.get("delta", 0.0)
                if node_id and not (
                    isinstance(result, str) and result.startswith("Error")
                ):
                    state["mastery_changes"][node_id] = (
                        state["mastery_changes"].get(node_id, 0.0) + delta
                    )
                    event_queue.put_nowait(
                        MasteryUpdatedEvent(node_id=node_id, delta=delta)
                    )

        return _hook

    def _build_tools(
        self,
        user_id: str,
        session_id: str,
        hook,
        is_immersive: bool,
    ) -> list:
        """组装 TutorAgent 可用的工具列表。"""
        tavily_key = get_setting(user_id, "tavily_api_key") or os.getenv(
            "TAVILY_API_KEY", ""
        )

        # 搜索工具额度 hook
        def _search_hook():
            check_and_consume(user_id, "search")

        tools = [
            get_current_time,
            SearchNodesTool(user_id),
            GetNodeTool(user_id),
            SessionCreateNodeTool(user_id, session_id, on_result_hook=hook),
            UpdateNodeTool(user_id),
            UpdateMasteryTool(user_id, on_result_hook=hook),
            CreateQuizTool(user_id, session_id, on_result_hook=hook),
        ]
        # AI 主导学习不需要卡片生成（课程 PDF 由 immersive_service 管理）
        if not is_immersive:
            tools.append(
                GenerateCardTool(
                    user_id=user_id,
                    session_id=session_id,
                    on_result_hook=hook,
                )
            )
        tools.extend(
            [
                # 内置网络工具（TavilySearch 注入额度 hook）
                TavilySearch(api_key=tavily_key, before_call_hook=_search_hook),
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
        return tools

    @staticmethod
    def _make_context_builder() -> SkillPromptContextBuilder:
        """创建 Tutor Agent 的 Context Builder。"""
        return SkillPromptContextBuilder(
            prompt_file=Path(__file__).parent.parent
            / "agents"
            / "prompts"
            / "tutor.md",
            skills_loader=SkillsLoader(workspace_skills_dir=_AGENTS_SKILLS_DIR),
        )

    def _persist_assistant_message(
        self,
        session: SessionSchema,
        final_content: str,
        state: Dict[str, Any],
        is_immersive: bool,
    ) -> None:
        """持久化 assistant 消息、会话节点列表、会话文件列表。"""
        mastery_changes: dict[str, float] = state["mastery_changes"]
        generated_file_ids: list[str] = state["generated_file_ids"]
        generated_files_meta: list[dict] = state["generated_files_meta"]
        created_node_ids: list[str] = state["created_node_ids"]
        created_quiz_ids: list[str] = state["created_quiz_ids"]

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
        self.session_repo.append_message(session.id, assistant_msg)

        # 更新会话涉及的节点列表
        if all_node_ids:
            merged = list(set((session.node_ids_covered or []) + all_node_ids))
            self.session_repo.update_nodes_covered(session.id, merged)

        # 将本轮生成的文件追加到 SessionSchema.files
        # 注意：AI 主导学习（immersive）的 session files 是课程章节 PDF，不应追加卡片
        if not is_immersive:
            for meta in generated_files_meta:
                self.session_repo.append_session_file(
                    session.id,
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
        session = self._assert_owner(user_id, session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")
        minutes = max(1, minutes)
        # 累加到 sessions.duration_minutes（不改变 status）
        self.session_repo.add_duration(session_id, minutes)
        # 同步更新今日学习日志
        all_node_ids = session.node_ids_covered or []
        self.study_log_repo.upsert_today(user_id, minutes, session_id, all_node_ids)
