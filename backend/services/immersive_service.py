"""
沉浸式学习（AI主导学习）服务层

架构：显式逐步编排（非 orchestrator 黑盒）
  Step 1: PlannerAgent → outline.json
  Step 2: 逐章循环:
    2a: ResearcherAgent → research.json
    2b: TexWriterAgent  → .tex + 插图 + .pdf
    2c: ExercisesAgent  → exercises.md
    2d: LLM 生成讲解稿 → speaker_notes.json
    2e: macOS Say TTS  → audio/frame_XXX.wav
    → 立即 yield chapter_done SSE 事件（前端实时渲染）
  Step 3: 知识图谱节点抽取
  Step 4: 写入 sessions + study_logs

每步完成后立即通过 SSE 推送给前端，前端可以在生成过程中浏览已完成的章节。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List

from agent_core.agent import (
    ReActAgent,
    AgentThinkEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    AgentFinalEvent,
)
from agent_core.context.profile_skill import ContextBuilderWithProfileAndSkill
from agent_core.context.simple import SimpleContextBuilder
from agent_core.layout import UserDataLayout
from agent_core.llm.base import BaseLLM
from agent_core.tool import (
    ToolRegistry,
    ReadFileTool,
    WriteFileTool,
    OpenAIImageGenTool,
    LatexPdfCompileTool,
    TavilySearch,
    WebFetch,
    ArxivSearch,
)
from agent_core.tool.tts_say import say_batch_synthesize

from config import DATA_DIR, SESSIONS_DIR
from database import get_db
from repositories.base import new_id, utcnow_str

# ── 资产归档 ─────────────────────────────────────────────────────
from services.asset_service import archive_immersive_chapter, pack_chapter_bundle

logger = logging.getLogger(__name__)

# ── 数据目录 ─────────────────────────────────────────────────────
IMMERSIVE_ROOT = DATA_DIR / "immersive"
IMMERSIVE_ROOT.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════
# SSE 事件
# ══════════════════════════════════════════════════════════════════


def _sse_event(type: str, **data) -> str:
    payload = {"type": type, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ══════════════════════════════════════════════════════════════════
# 数据库操作（sessions + study_logs + nodes）
# ══════════════════════════════════════════════════════════════════


def _create_immersive_session(topic: str, user_id: str = "default") -> str:
    session_id = new_id()
    now = utcnow_str()
    messages_file = str(SESSIONS_DIR / f"{session_id}.json")
    with get_db() as db:
        db.execute(
            """INSERT INTO sessions
              (id, user_id, title, topic, status, node_ids_covered,
               files, message_count, duration_minutes, messages_file, created_at, ended_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session_id,
                user_id,
                f"[AI课程] {topic}",
                topic,
                "active",
                "[]",
                "[]",
                0,
                0,
                messages_file,
                now,
                None,
            ),
        )
    Path(messages_file).parent.mkdir(parents=True, exist_ok=True)
    Path(messages_file).write_text("[]", encoding="utf-8")
    return session_id


def _finish_immersive_session(
    session_id: str,
    duration_minutes: int,
    node_ids: List[str],
    files: List[Dict],
) -> None:
    now = utcnow_str()
    today = datetime.now(timezone.utc).date().isoformat()
    with get_db() as db:
        db.execute(
            """UPDATE sessions SET status='completed', duration_minutes=?,
              node_ids_covered=?, files=?, ended_at=? WHERE id=?""",
            (
                duration_minutes,
                json.dumps(node_ids),
                json.dumps(files, ensure_ascii=False),
                now,
                session_id,
            ),
        )
        db.execute(
            """INSERT INTO study_logs (id, user_id, date, minutes, session_id, node_ids, created_at)
            VALUES (?, 'default', ?, ?, ?, ?, ?)""",
            (new_id(), today, duration_minutes, session_id, json.dumps(node_ids), now),
        )


def _register_immersive_documents(
    session_id: str,
    topic: str,
    chapter_results: List[Dict],
    node_ids: List[str],
    user_id: str = "default",
) -> None:
    """将 AI 课程生成的每章 PDF 登记到 documents 表，供文档管理页面展示。"""
    now = utcnow_str()
    with get_db() as db:
        for ch in chapter_results:
            if not ch.get("pdf_exists"):
                continue
            pdf_path = ch.get("pdf_path", "")
            if not pdf_path:
                continue

            # 计算文件大小
            abs_path = IMMERSIVE_ROOT / pdf_path
            file_size = abs_path.stat().st_size if abs_path.exists() else 0

            # 统计页数
            num_pages = ch.get("num_frames", 0)

            doc_id = new_id()
            # file_name: 只保存文件名（不含路径），与 DDL 一致
            pdf_file_name = (
                Path(pdf_path).name
                if pdf_path
                else f"chapter_{ch.get('chapter_id', '0')}.pdf"
            )
            db.execute(
                """INSERT INTO documents
                  (id, user_id, title, source, file_name, file_type, file_size,
                   status, total_pages, generated_from_session_id,
                   generation_prompt, generation_context,
                   node_ids, created_at, processed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc_id,
                    user_id,
                    f"[AI课程] {topic} — 第{ch.get('chapter_id', '?')}章 {ch.get('title', '')}",
                    "generated",
                    pdf_file_name,
                    "pdf",
                    file_size,
                    "ready",
                    num_pages,
                    session_id,
                    f"AI主导学习课程: {topic}",  # generation_prompt
                    json.dumps(
                        {
                            "topic": topic,
                            "chapter_id": ch.get("chapter_id"),
                            "chapter_title": ch.get("title", ""),
                            "immersive_pdf_path": str(abs_path),
                        },
                        ensure_ascii=False,
                    ),  # generation_context: 保存完整路径供检索
                    json.dumps(node_ids[:15], ensure_ascii=False),
                    now,
                    now,
                ),
            )
    logger.info(
        "AI课程文档登记完成：%d 个 PDF → documents 表",
        sum(1 for ch in chapter_results if ch.get("pdf_exists")),
    )


def _extract_and_create_nodes(
    session_id: str,
    topic: str,
    chapters: List[Dict],
    llm: BaseLLM,
    user_id: str = "default",
) -> List[Dict[str, str]]:
    all_kps = []
    for ch in chapters:
        for kp in ch.get("knowledge_points", []):
            all_kps.append({"kp": kp, "chapter": ch.get("title", "")})
    if not all_kps:
        return []

    kp_text = "\n".join(f"- [{item['chapter']}] {item['kp']}" for item in all_kps)
    prompt = (
        f"以下是关于「{topic}」课程各章节的知识点列表：\n{kp_text}\n\n"
        "请整理为知识图谱节点，要求：\n"
        "1. 去重合并相似概念\n2. 为每个节点提供简洁描述（50字内）\n"
        "3. 标注所属标签\n4. 严格输出 JSON 数组，每项：\n"
        '   {"title": "概念名", "description": "描述", "tags": ["标签"], "key_points": ["要点"]}\n'
        "5. 数量 5-15 个核心概念\n直接输出 JSON 数组。"
    )
    try:
        response = llm.think(
            [
                {"role": "system", "content": "你是知识图谱构建专家，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            config={"temperature": 0.3, "max_tokens": 3000},
        )
        match = re.search(r"\[[\s\S]*\]", response.content)
        if not match:
            return []
        nodes_data = json.loads(match.group())
        if not isinstance(nodes_data, list):
            return []
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("知识图谱抽取 LLM 调用失败: %s", e)
        return []

    created_nodes = []
    now = utcnow_str()
    due_date = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    with get_db() as db:
        for nd in nodes_data[:15]:
            title = nd.get("title", "").strip()
            if not title:
                continue
            existing = db.execute(
                "SELECT id FROM nodes WHERE user_id=? AND title=?", (user_id, title)
            ).fetchone()
            if existing:
                created_nodes.append(
                    {"id": existing["id"], "title": title, "existed": True}
                )
                continue
            node_id = new_id()
            content = {
                "key_points": nd.get("key_points", []),
                "examples": [],
                "common_mistakes": [],
                "summary": nd.get("description", ""),
            }
            origins = [
                {
                    "source_type": "session",
                    "source_id": session_id,
                    "source_title": f"[AI课程] {topic}",
                    "location": "AI课程自动抽取",
                    "excerpt": nd.get("description", "")[:200],
                }
            ]
            db.execute(
                """INSERT INTO nodes
                  (id, user_id, title, description, tags, content, origins, relations,
                   ease_factor, interval, repetitions, due_date, last_review_at,
                   mastery_level, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    node_id,
                    user_id,
                    title,
                    nd.get("description", ""),
                    json.dumps(nd.get("tags", [topic]), ensure_ascii=False),
                    json.dumps(content, ensure_ascii=False),
                    json.dumps(origins, ensure_ascii=False),
                    "[]",
                    2.5,
                    1,
                    0,
                    due_date,
                    None,
                    0.1,
                    now,
                    now,
                ),
            )
            created_nodes.append({"id": node_id, "title": title, "existed": False})

    logger.info("知识图谱抽取完成：%d 个节点", len(created_nodes))
    return created_nodes


# ══════════════════════════════════════════════════════════════════
# 子 Agent 构建（不再有 orchestrator，直接构建 4 个独立子 Agent）
# ══════════════════════════════════════════════════════════════════


def _build_sub_agents(layout: UserDataLayout):
    """构建 4 个独立子 Agent，返回字典。"""

    from services.llm_factory import get_llm

    planner = ReActAgent(
        llm=get_llm(),
        context_builder=ContextBuilderWithProfileAndSkill(
            workspace_dir=layout.root,
            base_prompt=(
                "你是一个专业的课程规划师。根据用户的学习主题，"
                "规划一份循序渐进的课程大纲。\n\n"
                "**工作流程**：\n"
                "1. 可选：使用搜索工具了解该主题的主流学习路线\n"
                "2. 设计 3-6 章课程大纲\n"
                "3. 使用 write_file 将大纲写入指定的 outline.json 路径\n"
                "4. 返回大纲的文本摘要\n\n"
                "**outline.json 格式**：\n"
                '{"topic": "主题", "overview": "介绍",\n'
                ' "chapters": [{"chapter_id": 1, "title": "标题",\n'
                '   "description": "目标", "knowledge_points": ["知识点"],\n'
                '   "estimated_hours": 1, "difficulty": "基础",\n'
                '   "search_keywords": ["关键词"]}]}\n\n'
                "要求：循序渐进，每章 3-6 个知识点，标注难度。"
            ),
        ),
        tool_registry=ToolRegistry(
            [
                TavilySearch(),
                ArxivSearch(),
                WebFetch(),
                WriteFileTool(),
            ]
        ),
        max_steps=10,
    )

    researcher = ReActAgent(
        llm=get_llm(),
        context_builder=SimpleContextBuilder(
            "你是信息检索助手。根据章节信息搜索资料，整理为 JSON 写入指定路径。\n"
            'JSON 格式：{"chapter_id": N, "chapter_title": "...",\n'
            '  "sources": [{"title": "...", "url": "...", "summary": "..."}],\n'
            '  "raw_text": "整合后参考资料（2000字内）"}\n'
            "要求：优先中文资料，保留关键知识点和公式，标注来源 URL。"
        ),
        tool_registry=ToolRegistry(
            [
                TavilySearch(),
                ArxivSearch(),
                WebFetch(),
                WriteFileTool(),
            ]
        ),
        max_steps=8,
    )

    tex_writer = ReActAgent(
        llm=get_llm(),
        context_builder=ContextBuilderWithProfileAndSkill(
            workspace_dir=layout.root,
            base_prompt=(
                "你是 LaTeX Beamer 讲义设计师。根据章节信息，从文件系统读取参考资料，生成教学插图，撰写 TeX 源码，编译为 PDF。\n"
                "严格遵循 tex_beamer_writing 技能中的所有格式规范和文件系统协议。"
            ),
        ),
        tool_registry=ToolRegistry(
            [
                ReadFileTool(),
                WriteFileTool(),
                _build_image_tool(),
                LatexPdfCompileTool(),
            ]
        ),
        max_steps=15,
    )

    exercises = ReActAgent(
        llm=get_llm(),
        context_builder=ContextBuilderWithProfileAndSkill(
            workspace_dir=layout.root,
            base_prompt=(
                "你是教育习题设计师。读取 TeX 讲义，生成 8-12 道配套习题写入 .md 文件。\n"
                "题型多样（选择题、填空题、简答题），难度由易到难。\n"
                "每道题后附带答案和解析，用 <details> 标签折叠。"
            ),
        ),
        tool_registry=ToolRegistry([ReadFileTool(), WriteFileTool()]),
        max_steps=8,
    )

    return {
        "planner": planner,
        "researcher": researcher,
        "tex_writer": tex_writer,
        "exercises": exercises,
    }


def _build_image_tool() -> OpenAIImageGenTool:
    """从 settings 表读取图像生成配置，构建 OpenAIImageGenTool 实例。

    如果配置读取失败，仍返回一个可用的实例（使用默认值），
    确保不会因为图片生成配置问题而阻断整个课程生成流程。
    """
    try:
        from database import get_setting
        import os

        api_key = get_setting("img_api_key") or os.getenv("IMG_API_KEY", "any")
        base_url = get_setting("img_base_url") or os.getenv(
            "IMG_BASE_URL", "http://localhost:8080/v1"
        )
        model = get_setting("img_model") or os.getenv("IMG_MODEL") or None
    except Exception as e:  # pylint: disable=broad-except
        logger.warning(
            "图片生成配置读取失败（将使用默认值，图片功能可能不可用）: %s", e
        )
        import os

        api_key = os.getenv("IMG_API_KEY", "any")
        base_url = os.getenv("IMG_BASE_URL", "http://localhost:8080/v1")
        model = os.getenv("IMG_MODEL") or None
    return OpenAIImageGenTool(api_key=api_key, base_url=base_url, model=model)


# ══════════════════════════════════════════════════════════════════
# TTS 后处理
# ══════════════════════════════════════════════════════════════════


def _generate_speaker_notes(llm: BaseLLM, tex_path: Path, num_pages: int) -> List[str]:
    if not tex_path.exists():
        return []
    tex_content = tex_path.read_text(encoding="utf-8")
    prompt = (
        f"以下是一份 LaTeX Beamer 讲义的完整源码，共约 {num_pages} 页 (frame)。\n\n"
        f"请你以一位**经验丰富的老师**的身份，为每一页写一段**讲解旁白**。\n\n"
        f"## 要求\n\n"
        f"1. **不要复读幻灯片上的文字**——学生自己能看到。你的角色是启发、引导、补充。\n"
        f"2. **循循善诱**：用提问、类比、生活化例子帮助学生理解，而非干巴巴念定义。\n"
        f"3. **该简短就简短**：如果这页只是标题页或目录页，一两句话即可（20-40字）；\n"
        f"   如果是核心知识点页，可以展开讲（80-150字）。\n"
        f"4. **准确**：不要编造公式含义或错误解释概念。\n"
        f"5. **口语化**：像老师在课堂上自然地说话，可以用'同学们'、'大家注意'、'我们来想一想'等。\n"
        f"6. **连贯**：前后页的讲解要有衔接，像一堂课的连续讲述。\n\n"
        f"## 输出格式\n\n"
        f"严格输出 JSON 数组，长度等于页数（{num_pages}），每项是一个字符串。\n"
        f"不要包含 Markdown 代码围栏，直接输出 JSON。\n\n"
        f"## 讲义源码\n\n"
        f"```tex\n{tex_content[:8000]}\n```"
    )
    response = llm.think(
        [
            {
                "role": "system",
                "content": (
                    "你是一位深受学生喜爱的大学老师，擅长用通俗易懂的语言讲解复杂知识。"
                    "你的讲解风格是：先抛出问题引发思考，再给出清晰解释，最后用一句话总结要点。"
                    "语气亲切自然，像面对面上课一样。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        config={"temperature": 0.6, "max_tokens": 5000},
    )
    try:
        match = re.search(r"\[[\s\S]*\]", response.content)
        if match:
            notes = json.loads(match.group())
            if isinstance(notes, list):
                return [str(n) for n in notes]
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("讲解稿解析失败: %s", e)
    return []


def _count_beamer_frames(tex_path: Path) -> int:
    if not tex_path.exists():
        return 0
    return tex_path.read_text(encoding="utf-8").count(r"\begin{frame}")


def _run_tts_for_chapter(
    chapter_dir: Path, speaker_notes: List[str]
) -> List[Dict[str, Any]]:
    if not speaker_notes:
        return []
    audio_dir = chapter_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    items = [
        {"text": note, "filename": f"frame_{i + 1:03d}.wav"}
        for i, note in enumerate(speaker_notes)
    ]
    result = say_batch_synthesize(
        items=items, output_dir=str(audio_dir), voice="Tingting", rate=180
    )
    return result.get("results", [])


def _to_rel_path(abs_path: str, root: Path = IMMERSIVE_ROOT) -> str:
    try:
        return str(Path(abs_path).relative_to(root))
    except ValueError:
        return abs_path


# ══════════════════════════════════════════════════════════════════
# 主流程：显式逐步编排（SSE 异步生成器）
# ══════════════════════════════════════════════════════════════════


async def immersive_generate(
    topic: str,
    user_profile: str = "",
) -> AsyncGenerator[str, None]:
    """
    AI主导学习 - 显式逐步编排。

    与之前的 orchestrator 黑盒不同，这里用 Python 代码显式控制每一步：
      planner → [逐章: researcher → tex_writer → exercises → TTS]
    每步完成后立即 yield SSE 事件，前端实时感知进度并渲染 PDF。

    SSE 事件类型：
      progress        { stage, pct, message }
      outline         { data }
      chapter_start   { index, total, chapter_id, title, stage }
      chapter_done    { index, total, data: {pdf_path, exercises_path, audio_files, ...} }
      nodes_extracted { nodes, new_count }
      done            { topic, session_id, chapters, ... }
      error           { message }
      agent_event     { agent_type, event_type, content, step }  # 新增：Agent事件
    """
    start_time = time.time()
    session_id = None

    try:
        # ── 0. 初始化 ────────────────────────────────────────────
        yield _sse_event(
            "progress", stage="init", pct=2, message=f"正在初始化课程「{topic}」..."
        )

        session_id = _create_immersive_session(topic)
        logger.info("沉浸式学习会话: %s (topic=%s)", session_id, topic)

        layout = UserDataLayout(root=IMMERSIVE_ROOT)
        layout.ensure_dirs()
        if user_profile:
            layout.profile_file.write_text(user_profile, encoding="utf-8")

        course = layout.course(topic)
        course.ensure_dirs()

        yield _sse_event(
            "progress", stage="init", pct=5, message="正在构建 Agent 团队..."
        )
        agents = await asyncio.to_thread(_build_sub_agents, layout)

        # ── 1. Planner：规划大纲 ─────────────────────────────────
        yield _sse_event(
            "progress",
            stage="planner",
            pct=8,
            message="📋 Planner：正在规划课程大纲...",
        )

        outline_path = course.outline_file
        planner_prompt = (
            f"请为「{topic}」规划课程大纲。\n将 outline.json 写入：{outline_path}"
        )

        # 使用 async_stream 替代 run
        yield _sse_event(
            "agent_event",
            agent_type="planner",
            event_type="start",
            content="开始规划课程大纲",
            step=0,
        )

        async for event in agents["planner"].async_stream(
            planner_prompt, skill_names=["pdf_courseware_orchestration"]
        ):
            if isinstance(event, AgentThinkEvent):
                yield _sse_event(
                    "agent_event",
                    agent_type="planner",
                    event_type="think",
                    content=event.content,
                    step=event.step,
                )
            elif isinstance(event, AgentToolCallEvent):
                yield _sse_event(
                    "agent_event",
                    agent_type="planner",
                    event_type="tool_call",
                    content=f"调用工具 {event.tool_name}: {event.arguments}",
                    step=event.step,
                )
            elif isinstance(event, AgentToolResultEvent):
                yield _sse_event(
                    "agent_event",
                    agent_type="planner",
                    event_type="tool_result",
                    content=f"工具 {event.tool_name} 执行完成",
                    step=event.step,
                )
            elif isinstance(event, AgentFinalEvent):
                yield _sse_event(
                    "agent_event",
                    agent_type="planner",
                    event_type="finish",
                    content="规划完成",
                    step=0,
                )

        logger.info("Planner 完成")

        # 读取大纲（load_outline 内部会自动清洗 LLM 输出中的非法控制字符）
        outline = course.load_outline()
        if not outline or not outline.get("chapters"):
            yield _sse_event("error", message="大纲生成失败，请重试")
            return

        # 重写清洗后的大纲到磁盘，确保后续所有读取都安全
        course.save_outline(outline)

        chapters = outline["chapters"]
        total_ch = len(chapters)

        yield _sse_event(
            "progress",
            stage="planner",
            pct=15,
            message=f"✅ 大纲完成，共 {total_ch} 章",
        )
        yield _sse_event("outline", data=outline)

        # ── 2. 逐章循环 ─────────────────────────────────────────
        from services.llm_factory import get_llm

        tts_llm = get_llm()
        chapter_results = []
        all_files_for_session = []
        pct_per_chapter = 75.0 / max(total_ch, 1)  # 15% ~ 90%

        for i, ch_info in enumerate(chapters):
            ch_id = ch_info.get("chapter_id", i + 1)
            ch_title = ch_info.get("title", f"第{ch_id}章")
            ch_base_pct = int(15 + pct_per_chapter * i)

            yield _sse_event(
                "chapter_start",
                index=i,
                total=total_ch,
                chapter_id=ch_id,
                title=ch_title,
                stage="researcher",
            )

            # ── 2a. Researcher ───────────────────────────────────
            researcher_pct = ch_base_pct
            yield _sse_event(
                "progress",
                stage="researcher",
                pct=researcher_pct,
                message=f"🔍 检索资料 ({i + 1}/{total_ch}): {ch_title}",
            )

            research_path = course.chapter_dir(ch_id) / "research.json"
            course.chapter_dir(ch_id).mkdir(parents=True, exist_ok=True)

            researcher_prompt = (
                f"为课程「{topic}」第 {ch_id} 章「{ch_title}」检索学习资料。\n"
                f"知识点：{', '.join(ch_info.get('knowledge_points', []))}\n"
                f"搜索关键词：{', '.join(ch_info.get('search_keywords', []))}\n"
                f"将结果写入：{research_path}"
            )

            yield _sse_event(
                "agent_event",
                agent_type="researcher",
                event_type="start",
                content=f"开始检索第{ch_id}章资料",
                step=0,
            )

            async for event in agents["researcher"].async_stream(researcher_prompt):
                if isinstance(event, AgentThinkEvent):
                    yield _sse_event(
                        "agent_event",
                        agent_type="researcher",
                        event_type="think",
                        content=event.content,
                        step=event.step,
                    )
                elif isinstance(event, AgentToolCallEvent):
                    yield _sse_event(
                        "agent_event",
                        agent_type="researcher",
                        event_type="tool_call",
                        content=f"调用工具 {event.tool_name}: {event.arguments}",
                        step=event.step,
                    )
                elif isinstance(event, AgentToolResultEvent):
                    yield _sse_event(
                        "agent_event",
                        agent_type="researcher",
                        event_type="tool_result",
                        content=f"工具 {event.tool_name} 执行完成",
                        step=event.step,
                    )
                elif isinstance(event, AgentFinalEvent):
                    yield _sse_event(
                        "agent_event",
                        agent_type="researcher",
                        event_type="finish",
                        content="检索完成",
                        step=0,
                    )

            logger.info("Researcher 完成: 第%d章 %s", ch_id, ch_title)

            # ── 2b. TeX Writer ───────────────────────────────────
            tex_pct = int(ch_base_pct + pct_per_chapter * 0.4)
            yield _sse_event(
                "progress",
                stage="tex",
                pct=tex_pct,
                message=f"📄 生成 PDF ({i + 1}/{total_ch}): {ch_title}",
            )

            tex_path = course.tex_file(ch_id)
            pdf_path = course.pdf_file(ch_id)
            images_dir = course.chapter_images_dir(ch_id)

            tex_prompt = (
                f"为课程「{topic}」第 {ch_id} 章「{ch_title}」生成 Beamer 讲义。\n"
                f"参考资料文件：{research_path}\n"
                f"TeX 输出路径：{tex_path}\n"
                f"图片输出目录：{images_dir}\n"
                f"知识点：{', '.join(ch_info.get('knowledge_points', []))}\n"
                f"难度：{ch_info.get('difficulty', '基础')}"
            )

            yield _sse_event(
                "agent_event",
                agent_type="tex_writer",
                event_type="start",
                content=f"开始生成第{ch_id}章PDF",
                step=0,
            )

            async for event in agents["tex_writer"].async_stream(
                tex_prompt, skill_names=["tex_beamer_writing"]
            ):
                if isinstance(event, AgentThinkEvent):
                    yield _sse_event(
                        "agent_event",
                        agent_type="tex_writer",
                        event_type="think",
                        content=event.content,
                        step=event.step,
                    )
                elif isinstance(event, AgentToolCallEvent):
                    yield _sse_event(
                        "agent_event",
                        agent_type="tex_writer",
                        event_type="tool_call",
                        content=f"调用工具 {event.tool_name}: {event.arguments}",
                        step=event.step,
                    )
                elif isinstance(event, AgentToolResultEvent):
                    yield _sse_event(
                        "agent_event",
                        agent_type="tex_writer",
                        event_type="tool_result",
                        content=f"工具 {event.tool_name} 执行完成",
                        step=event.step,
                    )
                elif isinstance(event, AgentFinalEvent):
                    yield _sse_event(
                        "agent_event",
                        agent_type="tex_writer",
                        event_type="finish",
                        content="PDF生成完成",
                        step=0,
                    )

            logger.info(
                "TeX Writer 完成: 第%d章 (PDF存在=%s)", ch_id, pdf_path.exists()
            )

            # ── 2c. Exercises ────────────────────────────────────
            exercises_pct = int(ch_base_pct + pct_per_chapter * 0.7)
            yield _sse_event(
                "progress",
                stage="exercises",
                pct=exercises_pct,
                message=f"✏️ 生成习题 ({i + 1}/{total_ch}): {ch_title}",
            )

            exercises_path = course.exercises_file(ch_id)

            exercises_prompt = (
                f"为课程「{topic}」第 {ch_id} 章「{ch_title}」生成配套习题。\n"
                f"TeX 讲义文件：{tex_path}\n"
                f"习题输出路径：{exercises_path}\n"
                f"知识点：{', '.join(ch_info.get('knowledge_points', []))}"
            )

            yield _sse_event(
                "agent_event",
                agent_type="exercises",
                event_type="start",
                content=f"开始生成第{ch_id}章习题",
                step=0,
            )

            async for event in agents["exercises"].async_stream(exercises_prompt):
                if isinstance(event, AgentThinkEvent):
                    yield _sse_event(
                        "agent_event",
                        agent_type="exercises",
                        event_type="think",
                        content=event.content,
                        step=event.step,
                    )
                elif isinstance(event, AgentToolCallEvent):
                    yield _sse_event(
                        "agent_event",
                        agent_type="exercises",
                        event_type="tool_call",
                        content=f"调用工具 {event.tool_name}: {event.arguments}",
                        step=event.step,
                    )
                elif isinstance(event, AgentToolResultEvent):
                    yield _sse_event(
                        "agent_event",
                        agent_type="exercises",
                        event_type="tool_result",
                        content=f"工具 {event.tool_name} 执行完成",
                        step=event.step,
                    )
                elif isinstance(event, AgentFinalEvent):
                    yield _sse_event(
                        "agent_event",
                        agent_type="exercises",
                        event_type="finish",
                        content="习题生成完成",
                        step=0,
                    )

            logger.info(
                "Exercises 完成: 第%d章 (存在=%s)", ch_id, exercises_path.exists()
            )

            # ── 2d. Speaker Notes + TTS ──────────────────────────
            tts_pct = int(ch_base_pct + pct_per_chapter * 0.85)
            num_frames = _count_beamer_frames(tex_path)
            speaker_notes = []
            audio_results = []

            if tex_path.exists() and num_frames > 0:
                yield _sse_event(
                    "progress",
                    stage="tts",
                    pct=tts_pct,
                    message=f"🔊 生成语音 ({i + 1}/{total_ch}): {ch_title} ({num_frames}页)",
                )

                speaker_notes = await asyncio.to_thread(
                    _generate_speaker_notes, tts_llm, tex_path, num_frames
                )

                if speaker_notes:
                    # 保存讲解稿
                    notes_path = course.chapter_dir(ch_id) / "speaker_notes.json"
                    notes_path.write_text(
                        json.dumps(speaker_notes, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )

                    # TTS 合成
                    audio_results = await asyncio.to_thread(
                        _run_tts_for_chapter, course.chapter_dir(ch_id), speaker_notes
                    )
                    logger.info(
                        "TTS 完成: 第%d章, %d 段语音", ch_id, len(audio_results)
                    )

            # ── 收集产物，发送 chapter_done ────────────────────────
            images = []
            if images_dir.exists():
                images = [
                    f.name
                    for f in images_dir.iterdir()
                    if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                ]

            pdf_rel = _to_rel_path(str(pdf_path)) if pdf_path.exists() else ""
            ex_rel = (
                _to_rel_path(str(exercises_path)) if exercises_path.exists() else ""
            )

            # 构建音频文件列表（含相对路径 URL）
            audio_files_data = []
            for r in audio_results:
                if r.get("success"):
                    audio_rel_dir = _to_rel_path(
                        str(course.chapter_dir(ch_id) / "audio")
                    )
                    audio_files_data.append(
                        {
                            "filename": r.get("filename", ""),
                            "url": f"/api/immersive/files/{audio_rel_dir}/{r.get('filename', '')}",
                            "duration_seconds": r.get("duration_seconds", 0),
                            "success": True,
                        }
                    )

            ch_result = {
                "chapter_id": ch_id,
                "title": ch_title,
                "knowledge_points": ch_info.get("knowledge_points", []),
                "pdf_exists": pdf_path.exists(),
                "pdf_path": pdf_rel,
                "exercises_exists": exercises_path.exists(),
                "exercises_path": ex_rel,
                "speaker_notes_count": len(speaker_notes),
                "audio_files": audio_files_data,
                "images": images,
                "images_count": len(images),
            }
            chapter_results.append(ch_result)

            if pdf_path.exists():
                all_files_for_session.append(
                    {
                        "file_id": pdf_rel,
                        "file_type": "pdf",
                        "title": f"第{ch_id}章 {ch_title}",
                    }
                )

            # ★ 立即推送 chapter_done —— 前端收到后马上渲染 PDF
            ch_done_pct = int(ch_base_pct + pct_per_chapter)
            yield _sse_event(
                "progress",
                stage="tex",
                pct=min(ch_done_pct, 90),
                message=f"✅ 第 {ch_id} 章完成: {ch_title}",
            )
            yield _sse_event(
                "chapter_done",
                index=i,
                total=total_ch,
                data=ch_result,
            )

            # ★ 异步归档本章产物到 data/assets/
            try:
                await asyncio.to_thread(
                    archive_immersive_chapter,
                    course.chapter_dir(ch_id),
                    topic,
                    str(ch_id),
                    session_id,
                )
            except Exception as e:  # pylint: disable=broad-except
                logger.warning("章节 %d 资产归档失败: %s", ch_id, e)

            # ★ 打包本章产物 (PDF + 语音 + 习题) 到 data/assets/files/
            try:
                bundle_path = await asyncio.to_thread(
                    pack_chapter_bundle,
                    course.chapter_dir(ch_id),
                    topic,
                    ch_title,
                    str(ch_id),
                    session_id,
                )
                if bundle_path:
                    logger.info("第%d章打包完成: %s", ch_id, bundle_path.name)
            except Exception as e:  # pylint: disable=broad-except
                logger.warning("章节 %d 打包失败: %s", ch_id, e)

        # ── 3. 知识图谱节点抽取 ──────────────────────────────────
        yield _sse_event(
            "progress", stage="nodes", pct=92, message="🧠 正在抽取知识图谱节点..."
        )

        created_nodes = await asyncio.to_thread(
            _extract_and_create_nodes,
            session_id,
            topic,
            chapters,
            tts_llm,
        )

        node_ids = [n["id"] for n in created_nodes]
        new_node_count = sum(1 for n in created_nodes if not n.get("existed"))

        if created_nodes:
            yield _sse_event(
                "nodes_extracted",
                nodes=[{"id": n["id"], "title": n["title"]} for n in created_nodes],
                new_count=new_node_count,
            )

        # ── 4. 完成 ─────────────────────────────────────────────
        duration_minutes = max(1, int((time.time() - start_time) / 60))

        _finish_immersive_session(
            session_id=session_id,
            duration_minutes=duration_minutes,
            node_ids=node_ids,
            files=all_files_for_session,
        )

        # 将每章 PDF 登记到 documents 表（文档管理页面可见）
        await asyncio.to_thread(
            _register_immersive_documents,
            session_id,
            topic,
            chapter_results,
            node_ids,
        )

        yield _sse_event("progress", stage="done", pct=100, message="🎉 全部完成！")
        yield _sse_event(
            "done",
            topic=topic,
            session_id=session_id,
            course_dir=str(course.course_dir),
            chapters=chapter_results,
            nodes_extracted=len(created_nodes),
            duration_minutes=duration_minutes,
        )

    except Exception as e:  # pylint: disable=broad-except
        logger.exception("沉浸式学习生成失败")
        yield _sse_event("error", message=str(e))
