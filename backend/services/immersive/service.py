"""沉浸式学习主编排（SSE 异步生成器）。

显式逐步编排，非 orchestrator 黑盒：
  Step 1: PlannerAgent → outline.json
  Step 2: 逐章循环（researcher → tex_writer → exercises → speaker_notes → TTS）
  Step 3: 知识图谱节点抽取
  Step 4: sessions/study_logs/documents 落库

每步完成后立即通过 SSE 推送给前端，前端可以在生成过程中浏览已完成的章节。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from agent_core.layout import CourseLayout, UserDataLayout, _slugify

from services.asset_service import archive_immersive_chapter, pack_chapter_bundle
from services.immersive.agents import build_sub_agents
from services.immersive.node_extractor import extract_and_persist_nodes
from services.immersive.persistence import (
    create_session,
    finish_session,
    register_chapter_documents,
)
from services.immersive.sse import sse_event, stream_agent_events
from services.immersive.tts import (
    count_beamer_frames,
    generate_speaker_notes,
    run_tts_for_chapter,
)
from services.immersive.utils import to_rel_path
from config import DOCUMENTS_DIR, COURSES_DIR

logger = logging.getLogger(__name__)


async def immersive_generate(
    topic: str,
    user_id: str,
    user_profile: str = "",
) -> AsyncGenerator[str, None]:
    """AI 主导学习 - 显式逐步编排（SSE）。

    SSE 事件类型：
      progress         { stage, pct, message }
      outline          { data }
      chapter_start    { index, total, chapter_id, title, stage }
      chapter_done     { index, total, data }
      nodes_extracted  { nodes, new_count }
      done             { topic, session_id, chapters, ... }
      error            { message }
      agent_event      { agent_type, event_type, content, step }
    """
    start_time = time.time()
    session_id = None

    try:
        # ── 0. 初始化 ────────────────────────────────────────────
        yield sse_event(
            "progress", stage="init", pct=2, message=f"正在初始化课程「{topic}」..."
        )

        session_id = create_session(topic, user_id=user_id)
        logger.info("沉浸式学习会话: %s (topic=%s)", session_id, topic)

        layout = UserDataLayout(root=DOCUMENTS_DIR)
        layout.ensure_dirs()
        if user_profile:
            layout.profile_file.write_text(user_profile, encoding="utf-8")

        course_slug = f"{_slugify(topic)}_{session_id}"
        course = CourseLayout(course_dir=COURSES_DIR / course_slug)
        course.ensure_dirs()

        yield sse_event(
            "progress", stage="init", pct=5, message="正在构建 Agent 团队..."
        )
        agents = build_sub_agents(layout, user_id=user_id)

        # ── 1. Planner：规划大纲 ─────────────────────────────────
        yield sse_event(
            "progress",
            stage="planner",
            pct=8,
            message="📋 Planner：正在规划课程大纲...",
        )

        outline_path = course.outline_file
        planner_prompt = (
            f"请为「{topic}」规划课程大纲。\n将 outline.json 写入：{outline_path}"
        )

        async for ev in stream_agent_events(
            agents["planner"],
            planner_prompt,
            "planner",
            skill_names=["pdf_courseware_orchestration"],
            start_msg="开始规划课程大纲",
            finish_msg="规划完成",
        ):
            yield ev

        logger.info("Planner 完成")

        # 读取大纲（load_outline 内部会自动清洗 LLM 输出中的非法控制字符）
        outline = course.load_outline()
        if not outline or not outline.get("chapters"):
            yield sse_event("error", message="大纲生成失败，请重试")
            return

        # 重写清洗后的大纲到磁盘，确保后续所有读取都安全
        course.save_outline(outline)

        chapters = outline["chapters"]
        total_ch = len(chapters)

        yield sse_event(
            "progress",
            stage="planner",
            pct=15,
            message=f"✅ 大纲完成，共 {total_ch} 章",
        )
        yield sse_event("outline", data=outline)

        # ── 2. 逐章循环 ─────────────────────────────────────────
        from services.llm_factory import get_llm

        tts_llm = get_llm(user_id)
        chapter_results = []
        all_files_for_session = []
        pct_per_chapter = 75.0 / max(total_ch, 1)  # 15% ~ 90%

        for i, ch_info in enumerate(chapters):
            ch_id = ch_info.get("chapter_id", i + 1)
            ch_title = ch_info.get("title", f"第{ch_id}章")
            ch_base_pct = int(15 + pct_per_chapter * i)

            yield sse_event(
                "chapter_start",
                index=i,
                total=total_ch,
                chapter_id=ch_id,
                title=ch_title,
                stage="researcher",
            )

            # ── 2a. Researcher ───────────────────────────────────
            yield sse_event(
                "progress",
                stage="researcher",
                pct=ch_base_pct,
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

            async for ev in stream_agent_events(
                agents["researcher"],
                researcher_prompt,
                "researcher",
                start_msg=f"开始检索第{ch_id}章资料",
                finish_msg="检索完成",
            ):
                yield ev

            logger.info("Researcher 完成: 第%d章 %s", ch_id, ch_title)

            # ── 2b. TeX Writer ───────────────────────────────────
            tex_pct = int(ch_base_pct + pct_per_chapter * 0.4)
            yield sse_event(
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

            async for ev in stream_agent_events(
                agents["tex_writer"],
                tex_prompt,
                "tex_writer",
                skill_names=["tex_beamer_writing"],
                start_msg=f"开始生成第{ch_id}章PDF",
                finish_msg="PDF生成完成",
            ):
                yield ev

            logger.info(
                "TeX Writer 完成: 第%d章 (PDF存在=%s)", ch_id, pdf_path.exists()
            )

            # ── 2c. Exercises ────────────────────────────────────
            exercises_pct = int(ch_base_pct + pct_per_chapter * 0.7)
            yield sse_event(
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

            async for ev in stream_agent_events(
                agents["exercises"],
                exercises_prompt,
                "exercises",
                start_msg=f"开始生成第{ch_id}章习题",
                finish_msg="习题生成完成",
            ):
                yield ev

            logger.info(
                "Exercises 完成: 第%d章 (存在=%s)", ch_id, exercises_path.exists()
            )

            # ── 2d. Speaker Notes + TTS ──────────────────────────
            tts_pct = int(ch_base_pct + pct_per_chapter * 0.85)
            num_frames = count_beamer_frames(tex_path)
            speaker_notes = []
            audio_results = []

            if tex_path.exists() and num_frames > 0:
                yield sse_event(
                    "progress",
                    stage="tts",
                    pct=tts_pct,
                    message=f"🔊 生成语音 ({i + 1}/{total_ch}): {ch_title} ({num_frames}页)",
                )

                speaker_notes = await asyncio.to_thread(
                    generate_speaker_notes, tts_llm, tex_path, num_frames
                )

                if speaker_notes:
                    notes_path = course.chapter_dir(ch_id) / "speaker_notes.json"
                    notes_path.write_text(
                        json.dumps(speaker_notes, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )

                    audio_results = await asyncio.to_thread(
                        run_tts_for_chapter, course.chapter_dir(ch_id), speaker_notes
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

            pdf_rel = to_rel_path(str(pdf_path)) if pdf_path.exists() else ""
            ex_rel = to_rel_path(str(exercises_path)) if exercises_path.exists() else ""

            audio_files_data = []
            for r in audio_results:
                if r.get("success"):
                    audio_rel_dir = to_rel_path(
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
                "num_frames": num_frames,
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
            yield sse_event(
                "progress",
                stage="tex",
                pct=min(ch_done_pct, 90),
                message=f"✅ 第 {ch_id} 章完成: {ch_title}",
            )
            yield sse_event(
                "chapter_done",
                index=i,
                total=total_ch,
                data=ch_result,
            )

            # ★ 异步归档本章产物到 data/assets/
            try:
                ch_dir = course.chapter_dir(ch_id)
                await asyncio.to_thread(
                    archive_immersive_chapter,
                    ch_dir,
                    topic,
                    ch_dir.name,  # 使用目录名 chapter_XX，与 archive_existing_assets 保持一致
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
        yield sse_event(
            "progress", stage="nodes", pct=92, message="🧠 正在抽取知识图谱节点..."
        )

        created_nodes = await asyncio.to_thread(
            extract_and_persist_nodes,
            session_id,
            topic,
            chapters,
            tts_llm,
            user_id,
        )

        node_ids = [n["id"] for n in created_nodes]
        new_node_count = sum(1 for n in created_nodes if not n.get("existed"))

        if created_nodes:
            yield sse_event(
                "nodes_extracted",
                nodes=[{"id": n["id"], "title": n["title"]} for n in created_nodes],
                new_count=new_node_count,
            )

        # ── 4. 完成 ─────────────────────────────────────────────
        duration_minutes = max(1, int((time.time() - start_time) / 60))

        finish_session(
            session_id=session_id,
            duration_minutes=duration_minutes,
            node_ids=node_ids,
            files=all_files_for_session,
            user_id=user_id,
        )

        # 将每章 PDF 登记到 documents 表（文档管理页面可见）
        await asyncio.to_thread(
            register_chapter_documents,
            session_id,
            topic,
            chapter_results,
            node_ids,
            user_id,
        )

        yield sse_event("progress", stage="done", pct=100, message="🎉 全部完成！")
        yield sse_event(
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
        yield sse_event("error", message=str(e))
