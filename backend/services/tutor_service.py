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
import re
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
from agents.tools.kg_tools import (
    KGProposeMissingConceptTool,
    KGRecordObservationTool,
    KGResolveTool,
    KGSearchTool,
)
from agent_core.agent.events import (
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
from services.llm_factory import get_llm, get_profile_llm
from services.context_orchestrator import (
    ContextOrchestrator,
    RECENT_MESSAGES,
    SUMMARIZE_TRIGGER_MESSAGES,
)
from services.quota import check_and_consume
from database import get_setting
from utils.log_safe import safe_log

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
        self.orchestrator = ContextOrchestrator(node_repo=self.node_repo)

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

        # ① 入口前置检索：把公共 KG 上下文作为一条 system 消息预置到历史最前面
        kg_pre_msg = self._build_kg_pre_context(user_message)
        if kg_pre_msg:
            chat_history = [kg_pre_msg, *chat_history]

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

        # ── 上下文编排：动态裁剪历史 + 主题感知注入（主路径零 LLM 调用）──
        # detail 携带 workspace（滚动摘要）与 node_ids_covered，供编排层使用。
        mode_hint = self._decide_interaction_mode(user_message, chat_history, session)
        dynamic_suffix = ""
        history_messages = chat_history
        try:
            pack = self.orchestrator.assemble(
                user_id=user_id,
                session=detail or session,
                chat_history=chat_history,
                user_message=user_message,
            )
            dynamic_suffix = self._append_interaction_mode_hint(
                pack.dynamic_suffix, mode_hint
            )
            history_messages = pack.history_messages
        except Exception:  # pylint: disable=broad-except
            # 编排失败时退化为现状行为（全量历史，仅注入轻量模式建议），不影响主对话
            logger.exception(
                "上下文编排失败，退化为全量历史 (session=%s)", safe_log(session_id)
            )
            dynamic_suffix = self._append_interaction_mode_hint("", mode_hint)

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
            context_builder=self._make_context_builder(user_id, dynamic_suffix),
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
                user_message, chat_history=history_messages
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

        # ── 异步触发画像更新（不阻塞主流程）─────────────────
        self._maybe_trigger_profile_update(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            assistant_reply=final_content,
            state=state,
            session=session,
        )

    # ── stream_chat 的内部辅助方法 ────────────────────────

    @staticmethod
    def _recent_assistant_generated_card(
        chat_history: list, session: SessionSchema | None = None
    ) -> bool:
        """最近两轮助教是否已经生成过 HTML 知识卡片。

        重构后 ``MessageArtifacts.files`` 里只存 ``file_id``（uuid），不再携带
        扩展名/路径，无法用 ``endswith('.html')`` 判断；统一改为：
        通过 ``session.files`` 里 ``file_type == 'html_card'`` + ``from_message_id``
        反查最近两轮 assistant 消息是否触发过 HTML 卡片生成。
        """
        # 收集最近两轮 assistant 消息的 id
        recent_assistant_ids: set[str] = set()
        for msg in reversed(list(chat_history or [])[-4:]):
            role = getattr(msg, "role", None) or (
                msg.get("role") if isinstance(msg, dict) else ""
            )
            if role != "assistant":
                continue
            msg_id = getattr(msg, "id", None) or (
                msg.get("id") if isinstance(msg, dict) else ""
            )
            if msg_id:
                recent_assistant_ids.add(str(msg_id))
        if not recent_assistant_ids:
            return False
        if session is None:
            return False
        for sf in session.files or []:
            try:
                file_type = getattr(sf, "file_type", None) or (
                    sf.get("file_type") if isinstance(sf, dict) else ""
                )
                from_msg = getattr(sf, "from_message_id", None) or (
                    sf.get("from_message_id") if isinstance(sf, dict) else ""
                )
            except Exception:  # pylint: disable=broad-except
                continue
            if file_type == "html_card" and str(from_msg) in recent_assistant_ids:
                return True
        return False

    def _decide_interaction_mode(
        self, user_message: str, chat_history: list, session: SessionSchema
    ) -> dict[str, str]:
        """快速学习右侧聊天栏的轻量意图判断：对话 / 卡片 / 测验 / 可视化。

        纯规则、零 LLM 调用，只作为 system prompt 的建议，不硬拦工具。
        """
        text = (user_message or "").strip().lower()
        compact = re.sub(r"\s+", "", text)
        recent_card = self._recent_assistant_generated_card(chat_history, session)
        first_turn = not any(
            (
                getattr(msg, "role", None)
                or (msg.get("role") if isinstance(msg, dict) else "")
            )
            == "assistant"
            for msg in (chat_history or [])
        )

        explicit_card = any(
            kw in compact
            for kw in (
                "生成卡片",
                "做张卡",
                "做一个卡片",
                "知识卡片",
                "整理成卡片",
                "总结成卡片",
                "生成一页",
                "可视化总结",
                "画一张",
                "画个图",
            )
        ) or (
            "卡片" in compact
            and any(v in compact for v in ("生成", "做", "整理", "总结", "来一张"))
        )
        new_knowledge_request = (
            "什么是" in compact and "为什么是" not in compact
        ) or any(
            kw in compact
            for kw in (
                "讲一下",
                "介绍一下",
                "系统讲",
                "详细讲",
                "原理",
                "怎么工作",
                "如何工作",
                "区别",
                "对比",
                "流程",
                "步骤",
            )
        )
        quiz_intent = any(
            kw in compact
            for kw in ("考考我", "出题", "练习", "测试一下", "小测", "刷题")
        )
        rich_content_required = any(
            kw in compact
            for kw in (
                "超过200字",
                "200字以上",
                "长篇",
                "详细解释",
                "系统解释",
                "完整讲",
                "全面讲",
                "展开讲",
                "梳理",
                "总结",
                "公式",
                "推导",
                "表格",
                "对比表",
                "图片",
                "插图",
                "图示",
                "图解",
                "流程图",
                "动画",
                "图文",
                "结构图",
                "示意图",
            )
        )
        viz_intent = any(
            kw in compact for kw in ("交互", "动态演示", "模拟", "拖动", "可视化演示")
        )
        dialogue_intent = any(
            kw in compact
            for kw in (
                "为什么",
                "什么意思",
                "没懂",
                "不懂",
                "换个说法",
                "举例",
                "再解释",
                "详细点",
                "简单说",
                "展开说",
                "刚才",
                "这个",
                "哪里",
                "怎么理解",
                "可以吗",
                "对吗",
                "是不是",
                "好的",
                "明白",
                "懂了",
            )
        )
        greeting_or_meta = any(
            kw in compact
            for kw in ("你好", "hello", "你是谁", "怎么用", "谢谢", "再见")
        )

        if first_turn and compact:
            mode, reason = (
                "card",
                "快速学习首轮固定生成知识卡片，并自主规划 3-5 页图文并茂的入门卡片组。",
            )
        elif quiz_intent:
            mode, reason = "quiz", "用户表达练习/测试意图，应生成交互式题目。"
        elif rich_content_required:
            mode, reason = (
                "card",
                "用户问题需要长篇、公式、表格、图片或动画等结构化展示，适合生成知识卡片。",
            )
        elif viz_intent:
            mode, reason = (
                "visualization",
                "用户表达动态/交互可视化意图，优先生成交互可视化。",
            )
        elif explicit_card:
            mode, reason = "card", "用户明确要求生成或整理成知识卡片。"
        elif greeting_or_meta:
            mode, reason = "chat", "用户是闲聊或元问题，直接对话。"
        elif recent_card and dialogue_intent:
            mode, reason = "chat", "近期已生成过卡片，当前是跟进追问，优先对话解释。"
        elif new_knowledge_request and not recent_card:
            mode, reason = "card", "用户提出新的知识讲解请求，适合沉淀为知识卡片。"
        elif dialogue_intent:
            mode, reason = "chat", "用户在追问/澄清/确认理解，优先对话交流。"
        elif len(compact) <= 18:
            mode, reason = "chat", "输入较短且意图不明确，先对话澄清。"
        else:
            mode, reason = "card", "用户提出新的实质知识学习请求，可沉淀为知识卡片。"

        return {"mode": mode, "reason": reason}

    @staticmethod
    def _append_interaction_mode_hint(dynamic_suffix: str, hint: dict[str, str]) -> str:
        mode = hint.get("mode", "chat")
        labels = {
            "chat": "对话交流",
            "card": "生成知识卡片",
            "quiz": "生成练习题",
            "visualization": "生成交互可视化",
        }
        guidance = {
            "chat": "本轮优先直接用文字交流，不要生成新的知识卡片；除非用户再次明确要求卡片。",
            "card": "本轮应生成知识卡片。若是快速学习首轮：必须先自主判断需要几页，正常生成 3-5 张图文并茂的入门卡片组；根据用户问题复杂度和画像习惯调整页数（简单主题 3 张，常规主题 4 张，复杂主题 5 张）。若用户问题需要超过 200 字解释，或包含公式、推导、表格、图片、插图、动画、流程图等结构化展示，也应生成知识卡片。后续轮次再按语境决定是否只聊天或追加少量卡片。",
            "quiz": "本轮优先调用 create_quiz 生成交互式题目，不要在文字里直接写题目和答案。",
            "visualization": "本轮优先考虑 generate_interactive_viz；如还需要沉淀静态知识，再生成一张卡片。",
        }
        block = (
            "## 本轮交互建议\n\n"
            f"推荐模式：{labels.get(mode, mode)}\n"
            f"判断依据：{hint.get('reason', '')}\n"
            f"执行要求：{guidance.get(mode, guidance['chat'])}"
        )
        return "\n\n---\n\n".join(
            p for p in [(dynamic_suffix or "").strip(), block] if p
        )

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
                            file_type = "html_card"
                        else:
                            file_id = result.strip()
                            file_type = "viz"
                    except (json.JSONDecodeError, AttributeError):
                        file_id = ""
                        file_type = "upload"
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
                except (json.JSONDecodeError, AttributeError) as e:
                    logger.exception("create_node hook 调用失败, error: %s", str(e))

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
                except (json.JSONDecodeError, AttributeError) as e:
                    logger.exception("create_quiz hook 调用失败, error: %s", str(e))

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
            # 公共知识图谱（KG）：检索 + 提议缺失概念 + 写观察
            KGSearchTool(),
            KGResolveTool(),
            KGProposeMissingConceptTool(user_id, session_id),
            KGRecordObservationTool(user_id, session_id),
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
    def _make_context_builder(
        user_id: str = "", dynamic_suffix: str = ""
    ) -> SkillPromptContextBuilder:
        """创建 Tutor Agent 的 Context Builder。

        画像/学习状态由上层 ContextOrchestrator 按当前话题动态产出为 dynamic_suffix，
        本方法只负责把它追加到 system prompt 末尾（替代旧的"静态整段画像注入"）。
        dynamic_suffix 为空时（无画像/编排失败）退化为纯角色提示。
        """
        suffix = (dynamic_suffix or "").strip()

        class _TutorContextBuilderWithProfile(SkillPromptContextBuilder):
            """在 SkillPromptContextBuilder 基础上追加动态上下文（画像激活 + 学习状态）。"""

            def build_system_prompt(self, **kwargs):
                base = super().build_system_prompt(**kwargs)
                if suffix:
                    return base + "\n\n---\n\n" + suffix
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
                    file_type=meta.get("file_type", "html_card"),
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
        """异步执行画像 consolidate，从最近对话中提取用户信息并落入结构化记忆。"""
        try:
            from services.profile_service import ProfileMemoryService

            # 获取最近的对话消息（最多取最近 10 条）
            detail = self.session_repo.get_detail(session_id)
            if not detail or not detail.messages:
                return

            recent_msgs = detail.messages[-10:]
            messages = []
            history_summary = (
                (detail.workspace or {}).get("history_summary") or ""
            ).strip()
            if history_summary:
                messages.append(
                    {
                        "role": "system",
                        "content": "既往对话短期摘要：" + history_summary,
                    }
                )
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
            profile_llm = get_profile_llm(user_id)
            success = await ProfileMemoryService().consolidate_from_messages(
                user_id, messages, profile_llm
            )
            if success:
                logger.info("画像 consolidate 成功 (session=%s)", safe_log(session_id))
            else:
                logger.warning(
                    "画像 consolidate 失败 (session=%s)", safe_log(session_id)
                )

            # 画像更新后，按需增量生成会话滚动摘要（复用同一异步链路）
            await self._maybe_update_rolling_summary(user_id, session_id, llm)

        except Exception:  # pylint: disable=broad-except
            logger.exception("画像 consolidate 异常 (session=%s)", safe_log(session_id))

    # ── KG 前置检索（钩子①）────────────────────────────────────

    def _build_kg_pre_context(self, user_message: str):
        """同步检索 KG，把命中结果作为一条 system 消息返回（用于预置到 chat_history 最前）。

        - 失败 / 超时 / 命中不足 → 返回 None，不插入任何上下文。
        - 设计为在主对话开始前给 LLM 提供"集体潜意识"参考。
        """
        try:
            from kg.config import (
                KG_CHAT_PRERAG_ENABLED,
                KG_CHAT_PRERAG_TIMEOUT_MS,
                KG_CHAT_PRERAG_TOP_CONCEPTS,
                KG_CHAT_PRERAG_TOP_FACETS_PER_CONCEPT,
            )
        except Exception:  # pylint: disable=broad-except
            return None
        if not KG_CHAT_PRERAG_ENABLED:
            return None
        if not user_message or len(user_message.strip()) < 2:
            return None

        try:
            from concurrent.futures import (
                ThreadPoolExecutor,
                TimeoutError as FTTimeoutError,
            )

            from kg import RetrieveRequest
            from services import kg_facade

            req = RetrieveRequest(
                query=user_message.strip(),
                need_facets=True,
                graph_expand=True,
                top_k_facets_per_concept=KG_CHAT_PRERAG_TOP_FACETS_PER_CONCEPT,
                anchor_max_entries=KG_CHAT_PRERAG_TOP_CONCEPTS,
                max_subgraph_size=KG_CHAT_PRERAG_TOP_CONCEPTS + 4,
            )
            # 用线程池跑 + 超时；KG 检索本身是同步阻塞 IO（向量库 + sqlite）
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(kg_facade.retrieve, req)
                try:
                    resp = fut.result(timeout=KG_CHAT_PRERAG_TIMEOUT_MS / 1000.0)
                except FTTimeoutError:
                    logger.info("KG 前置检索超时 (>%d ms)", KG_CHAT_PRERAG_TIMEOUT_MS)
                    return None
        except Exception:  # pylint: disable=broad-except
            logger.exception("KG 前置检索异常")
            return None

        if not resp or resp.degraded or not resp.concepts:
            return None

        lines: list[str] = [
            "## 公共知识图谱参考（系统自动检索）",
            "> 以下内容由系统从公共知识图谱中按当前问题检索而来，仅供参考；",
            "如与用户问题无关请忽略，不要在回复中提到「知识图谱」字样。",
            "",
            "### 相关概念",
        ]
        for c in resp.concepts:
            summary = (c.summary or "").strip()
            lines.append(f"- **{c.canonical_name}** ({c.id}): {summary}")
        if resp.facets:
            lines.append("")
            lines.append("### 相关切面")
            for f in resp.facets:
                lines.append(
                    f"- [{f.kind}] (concept={f.concept_id}, "
                    f"conf={f.confidence:.2f}, sup={f.support_count}) {f.content}"
                )
        kg_text = "\n".join(lines).strip()

        return MessageSchema(
            id=f"kg-ctx-{uuid.uuid4().hex[:8]}",
            role="system",
            content=kg_text,
            created_at=datetime.now(timezone.utc),
        )

    async def _maybe_update_rolling_summary(
        self, user_id: str, session_id: str, llm: Any
    ) -> None:
        """增量更新会话滚动摘要并落入 session.workspace。

        策略（防 N+1 LLM）：仅当累计消息数超过阈值、且自上次摘要以来又积累了
        新的"窗口外旧消息"时，才用一次 LLM 把这些旧消息追加压缩进既有摘要。
        保留最近 RECENT_MESSAGES 条原文不摘要。摘要失败静默跳过，下轮重试。
        """
        try:
            detail = self.session_repo.get_detail(session_id)
            if not detail or not detail.messages:
                return
            messages = detail.messages
            total = len(messages)
            if total < SUMMARIZE_TRIGGER_MESSAGES:
                return

            workspace = detail.workspace or {}
            try:
                summarized_until = int(workspace.get("summarized_until") or 0)
            except (TypeError, ValueError):
                summarized_until = 0
            prev_summary = (workspace.get("history_summary") or "").strip()

            # 摘要覆盖到 total - RECENT_MESSAGES，保留最近窗口原文
            cutoff = total - RECENT_MESSAGES
            if cutoff <= summarized_until:
                return  # 没有新的可摘要内容

            old_msgs = messages[summarized_until:cutoff]
            convo = self._format_messages_for_summary(old_msgs)
            if not convo.strip():
                return

            sys_prompt = (
                "你是对话摘要助手。请把【既有摘要】与【新增对话】整合为一段连贯的中文摘要，"
                "保留对后续辅导有价值的信息：用户的学习目标、已讲过的知识点与结论、"
                "用户表现出的薄弱点/偏好、待办或悬而未决的问题。"
                "去除寒暄与冗余，控制在 300 字以内，只输出摘要正文。"
            )
            user_prompt = (
                f"## 既有摘要\n{prev_summary or '（无）'}\n\n## 新增对话\n{convo}"
            )
            response = await llm.async_think(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
            if response.is_error or not (response.content or "").strip():
                logger.warning(
                    "滚动摘要生成失败，跳过 (session=%s)", safe_log(session_id)
                )
                return

            new_summary = response.content.strip()
            self.session_repo.update_workspace(
                session_id,
                workspace={
                    "history_summary": new_summary,
                    "summarized_until": cutoff,
                },
            )
            logger.info(
                "[Orchestrator] 滚动摘要更新 (session=%s) cutoff=%d summary=%dch",
                safe_log(session_id),
                cutoff,
                len(new_summary),
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception("滚动摘要更新异常 (session=%s)", safe_log(session_id))

    @staticmethod
    def _format_messages_for_summary(msgs: list) -> str:
        """把 MessageSchema/dict 列表格式化为 role: content 文本（供摘要 LLM）。"""
        lines: list[str] = []
        for m in msgs:
            role = m.role if hasattr(m, "role") else m.get("role", "user")
            content = m.content if hasattr(m, "content") else m.get("content", "")
            content = (content or "").strip()
            if not content:
                continue
            speaker = {"user": "用户", "assistant": "助教", "system": "系统"}.get(
                role, role
            )
            lines.append(f"{speaker}：{content}")
        return "\n".join(lines)

    def record_duration(self, user_id: str, session_id: str, minutes: int) -> None:
        """前端离开会话页面时调用，记录本次会话的学习时长"""
        session = self._assert_owner(user_id, session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")
        minutes = max(1, minutes)
        # 累加到 sessions.duration_minutes（不改变 status）
        self.session_repo.add_duration(session_id, minutes)
        # 同步更新今日学习日志，并异步画像总览中的学习行为快照
        all_node_ids = session.node_ids_covered or []
        self.study_log_repo.upsert_today(user_id, minutes, session_id, all_node_ids)
        try:
            from repositories import ProfileOverviewRepository

            ProfileOverviewRepository().refresh_source_snapshot(user_id)
        except Exception:
            logger.exception("刷新画像学习行为快照失败 (user=%s)", safe_log(user_id))
