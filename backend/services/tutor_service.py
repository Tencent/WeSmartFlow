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
from agents.tools.generate_html_card import GenerateHtmlCardTool
from agents.tools.generate_viz import GenerateInteractiveVizTool
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

        # 状态累加器
        # 状态累加器（hook 与 stream 共享）
        state: Dict[str, Any] = {
            "mastery_changes": {},
            "ordered_files": [],  # 按 index 插槽统一管理三种卡片顺序
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
            context_builder=self._make_context_builder(user_id),
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

        # ── 异步触发画像更新（不阻塞主流程）──────────────────────
        self._maybe_trigger_profile_update(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            assistant_reply=final_content,
            state=state,
            session=session,
        )

    # ── stream_chat 的内部辅助方法 ────────────────────────

    def _validate_session(self, user_id: str, session_id: str) -> SessionSchema:
        """校验会话存在、属于本人、且处于可对话状态，返回 session 对象。"""
        session = self._assert_owner(user_id, session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")
        # 允许所有会话继续对话（包括 completed 状态），自动重新激活
        if session.status != "active":
            self.session_repo.update_status(session_id, "active")
            session.status = "active"
        return session

    @staticmethod
    def _make_result_hook(state: Dict[str, Any], event_queue: asyncio.Queue):
        """构造工具结果 hook：收集副作用并向 event_queue 推入业务事件。"""

        def _hook(
            tool_name: str, params: Dict[str, Any], result: Any, index: int = 0
        ) -> None:
            logger.info(
                f"Tool {tool_name} called with params {params}, got result {result}"
            )
            if tool_name in ("generate_html_card", "generate_interactive_viz"):
                if isinstance(result, str) and not result.startswith("Error"):
                    try:
                        # generate_html_card 返回 JSON {file_id, script}
                        # generate_interactive_viz 返回纯 viz_id 字符串
                        if tool_name == "generate_html_card":
                            data = json.loads(result)
                            file_id = data.get("file_id", "")
                            file_type = "html"
                        else:
                            file_id = result.strip()
                            file_type = "viz"
                    except (json.JSONDecodeError, AttributeError):
                        file_id = ""
                        file_type = "empty"
                    if file_id:
                        while len(state["ordered_files"]) <= index:
                            state["ordered_files"].append(None)
                        file_title = params.get("title", "")
                        state["ordered_files"][index] = {
                            "file_id": file_id,
                            "title": file_title,
                            "file_type": file_type,
                        }
                        event_queue.put_nowait(
                            FileCreatedEvent(
                                file_id=file_id, title=file_title, file_type=file_type
                            )
                        )

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
                        # 用同样的 index 插槽写入 ordered_files，保证与 html/viz 的相对顺序
                        while len(state["ordered_files"]) <= index:
                            state["ordered_files"].append(None)
                        question = params.get("question", "")
                        quiz_title = (
                            (question[:20] + "…")
                            if len(question) > 20
                            else (question or "练习题")
                        )
                        state["ordered_files"][index] = {
                            "file_id": data["quiz_id"],
                            "title": quiz_title,
                            "file_type": "quiz",
                        }
                        event_queue.put_nowait(
                            FileCreatedEvent(
                                file_id=data["quiz_id"],
                                title=quiz_title,
                                file_type="quiz",
                            )
                        )
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
        # HTML 卡片 / 交互可视化：交互式学习和沉浸式学习的聊天都需要
        tools.append(
            GenerateHtmlCardTool(
                user_id=user_id,
                session_id=session_id,
                on_result_hook=hook,
            )
        )
        tools.append(
            GenerateInteractiveVizTool(
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
    def _make_context_builder(user_id: str = "") -> SkillPromptContextBuilder:
        """创建 Tutor Agent 的 Context Builder（含用户画像注入）。"""
        from config import DOCUMENTS_DIR
        from agent_core.layout import UserDataLayout

        layout = UserDataLayout(root=DOCUMENTS_DIR, user_id=user_id)
        profile_file = layout.profile_file

        # 读取用户画像，追加到 tutor prompt 之后
        profile_text = ""
        if profile_file.exists():
            profile_text = profile_file.read_text(encoding="utf-8").strip()
        # fallback: 如果用户专属画像不存在，尝试读取旧的全局画像（迁移兼容）
        if not profile_text and user_id:
            legacy_file = layout.profile_dir / "profile.md"
            if legacy_file.exists():
                profile_text = legacy_file.read_text(encoding="utf-8").strip()

        class _TutorContextBuilderWithProfile(SkillPromptContextBuilder):
            """在 SkillPromptContextBuilder 基础上追加用户画像。"""

            def build_system_prompt(self, **kwargs):
                base = super().build_system_prompt(**kwargs)
                if profile_text:
                    return base + "\n\n---\n\n## 用户画像\n\n" + profile_text
                return base

        return _TutorContextBuilderWithProfile(
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
        created_node_ids: list[str] = state["created_node_ids"]

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
                files=[
                    f["file_id"]
                    for f in state.get("ordered_files", [])
                    if f is not None
                ],
                new_nodes=new_nodes,
                node_refs=node_refs,
                mastery_delta=mastery_changes,
                quiz_ids=state["created_quiz_ids"],
            ),
        )
        self.session_repo.append_message(session.id, assistant_msg)

        # 更新会话涉及的节点列表
        if all_node_ids:
            merged = list(set((session.node_ids_covered or []) + all_node_ids))
            self.session_repo.update_nodes_covered(session.id, merged)

        # 将本轮生成的文件追加到 SessionSchema.files
        # 按工具调用顺序（ordered_files）统一 append，保证 html/viz/quiz 混合排列
        logger.info(
            f"本轮生成文件列表（按工具调用顺序）: {state.get('ordered_files', [])}"
        )
        ordered_files: list[dict] = [
            f for f in state.get("ordered_files", []) if f is not None
        ]
        for meta in ordered_files:
            self.session_repo.append_session_file(
                session.id,
                SessionFile(
                    file_id=meta["file_id"],
                    title=meta["title"],
                    file_type=meta.get("file_type", "html"),
                    created_at=now,
                    from_message_id=assistant_msg_id,
                ),
            )

    # ── 画像自动更新 ─────────────────────────────────────────────

    # 类级别消息计数器（session_id -> 未触发consolidate的消息数）
    _msg_count_since_consolidate: Dict[str, int] = {}
    # 触发阈值：累积 N 轮对话后触发一次 consolidate
    _CONSOLIDATE_THRESHOLD = 6
    # 有效交互关键词（检测到时立即触发）
    _EFFECTIVE_SIGNALS = [
        "不懂",
        "不理解",
        "太难",
        "太简单",
        "能简单点",
        "能详细点",
        "我之前学过",
        "我的背景",
        "我擅长",
        "我不擅长",
        "我喜欢",
        "我讨厌",
        "我习惯",
        "帮我",
        "我想学",
        "我的目标",
    ]

    def _maybe_trigger_profile_update(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_reply: str,
        state: Dict[str, Any],
        session: SessionSchema,
    ) -> None:
        """检测是否应触发画像更新，满足条件时异步执行 consolidate。

        触发条件（满足任一即可）：
        1. 累积消息数达到阈值（6 轮对话）
        2. 用户消息中包含有效交互信号关键词
        3. 本轮有 mastery_changes（说明有知识点掌握度变化）
        """
        # 累积计数
        count = self._msg_count_since_consolidate.get(session_id, 0) + 1
        self._msg_count_since_consolidate[session_id] = count

        should_trigger = False

        # 条件1：累积达到阈值
        if count >= self._CONSOLIDATE_THRESHOLD:
            should_trigger = True

        # 条件2：有效交互信号
        if not should_trigger:
            msg_lower = user_message.lower()
            for signal in self._EFFECTIVE_SIGNALS:
                if signal in msg_lower:
                    should_trigger = True
                    break

        # 条件3：有 mastery 变化
        if not should_trigger and state.get("mastery_changes"):
            should_trigger = True

        if not should_trigger:
            return

        # 重置计数
        self._msg_count_since_consolidate[session_id] = 0

        # 异步执行 consolidate（不阻塞主流程）
        asyncio.ensure_future(self._do_consolidate(user_id, session_id, session))

    async def _do_consolidate(
        self, user_id: str, session_id: str, session: SessionSchema
    ) -> None:
        """异步执行画像 consolidate，从最近对话中提取用户信息。"""
        try:
            from config import DOCUMENTS_DIR
            from agent_core.layout import UserDataLayout
            from agent_core.memory.profile import FileUserProfileStore

            layout = UserDataLayout(root=DOCUMENTS_DIR, user_id=user_id)
            layout.ensure_dirs()
            profile_store = FileUserProfileStore(
                profile_file=layout.profile_file,
                history_file=layout.profile_history_file,
            )

            # 获取最近的对话消息（最多取最近 10 条）
            detail = self.session_repo.get_detail(session_id)
            if not detail or not detail.messages:
                return

            recent_msgs = detail.messages[-10:]
            messages = []
            for msg in recent_msgs:
                role = msg.role if hasattr(msg, "role") else msg.get("role", "user")
                content = (
                    msg.content if hasattr(msg, "content") else msg.get("content", "")
                )
                messages.append({"role": role, "content": content})

            # 如果是沉浸式课程，在消息前加 topic 上下文
            is_immersive = (session.title or "").startswith("[AI课程]")
            if is_immersive:
                topic = (
                    (session.topic or session.title or "")
                    .replace("[AI课程]", "")
                    .strip()
                )
                if topic:
                    messages.insert(
                        0,
                        {
                            "role": "system",
                            "content": f"以下对话发生在用户学习「{topic}」课程的过程中。",
                        },
                    )

            llm = get_llm(user_id)
            success = await profile_store.consolidate(messages, llm)
            if success:
                logger.info("画像 consolidate 成功 (session=%s)", session_id)
            else:
                logger.warning("画像 consolidate 失败 (session=%s)", session_id)

        except Exception:  # pylint: disable=broad-except
            logger.exception("画像 consolidate 异常 (session=%s)", session_id)

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
