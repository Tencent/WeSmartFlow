"""沉浸式学习主编排（SSE 异步生成器）。

显式逐步编排，非 orchestrator 黑盒：
  Step 1: PlannerAgent → outline.json
  Step 2: 逐章循环（researcher → tex_writer → exercises → speaker_notes → TTS）
  Step 3: 知识图谱节点抽取
  Step 4: sessions/study_logs/documents 落库

每步完成后立即通过 SSE 推送给前端，前端可以在生成过程中浏览已完成的章节。
"""

from __future__ import annotations

import os
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import AsyncGenerator

from agent_core.agent import ReActAgent
from agent_core.context.simple import SimpleContextBuilder
from agent_core.tool import (
    ArxivSearch,
    TavilySearch,
    ToolRegistry,
    WebFetch,
    WriteFileTool,
)
from database import get_setting

from agent_core.layout import CourseLayout, UserDataLayout, _slugify
from agent_core.tool.pdf_compile import validate_pdf_file

from services.asset_service import archive_immersive_chapter, pack_chapter_bundle
from services.immersive.agents import build_sub_agents
from services.immersive.node_extractor import extract_and_persist_nodes
from services.immersive.persistence import (
    create_session,
    register_chapter_documents,
    register_single_chapter_document,
    register_chapter_overview_md,
    update_workspace,
    upsert_canvas_block,
    append_session_file,
)
from services.immersive.sse import sse_event, stream_agent_events
from services.immersive.tts import (
    count_beamer_frames,
    generate_speaker_notes,
    run_tts_for_chapter,
)
from services.immersive.utils import to_rel_path
from config import DOCUMENTS_DIR, COURSES_DIR
from services.llm_factory import get_llm

logger = logging.getLogger(__name__)


def _pdf_is_ready(pdf_path: Path) -> bool:
    """判断 PDF 是否真实可交付，而不是仅仅存在。"""
    error = validate_pdf_file(pdf_path)
    if error:
        if pdf_path.exists():
            logger.warning("PDF 校验失败，将视为不可用: %s，原因: %s", pdf_path, error)
        return False
    return True


def _file_is_ready(path: Path, min_size: int = 50) -> bool:
    """判断普通文本/媒体产物是否已实际落盘。"""
    try:
        return path.exists() and path.is_file() and path.stat().st_size > min_size
    except OSError:
        return False


def _chapter_artifact_status(
    course: CourseLayout,
    ch_info: dict,
    index: int,
    enable_audio: bool = False,
    enable_exercises: bool = True,
) -> dict:
    """扫描章节磁盘产物，返回恢复生成时可信的真实状态。"""
    ch_id = ch_info.get("chapter_id", index + 1)
    chapter_dir = course.chapter_dir(ch_id)
    research_path = chapter_dir / "research.json"
    tex_path = course.tex_file(ch_id)
    pdf_path = course.pdf_file(ch_id)
    exercises_path = course.exercises_file(ch_id)
    overview_path = chapter_dir / f"chapter_{ch_id:02d}_overview.md"
    notes_path = chapter_dir / "speaker_notes.json"
    audio_dir = chapter_dir / "audio"

    pdf_error = validate_pdf_file(pdf_path)
    tex_ready = _file_is_ready(tex_path)
    num_frames = count_beamer_frames(tex_path) if tex_ready else 0
    audio_files = (
        sorted(f.name for f in audio_dir.iterdir() if f.suffix.lower() == ".wav")
        if audio_dir.exists()
        else []
    )

    checks = {
        "research": _file_is_ready(research_path),
        "tex": tex_ready,
        "pdf": pdf_error is None,
        "exercises": _file_is_ready(exercises_path),
        "overview_md": _file_is_ready(overview_path),
        "speaker_notes": _file_is_ready(notes_path, min_size=2),
        "audio": num_frames > 0 and len(audio_files) >= num_frames,
    }
    required_keys = ["research", "tex", "pdf"]
    if enable_exercises:
        required_keys.append("exercises")
    if enable_audio:
        required_keys.extend(["speaker_notes", "audio"])
    required_checks = {key: checks[key] for key in required_keys}
    missing = [name for name, ready in required_checks.items() if not ready]
    optional_keys = ["overview_md"]
    optional_missing = [name for name in optional_keys if not checks[name]]
    if pdf_error and pdf_path.exists():
        missing.append(f"pdf_invalid: {pdf_error}")

    files = []
    if checks["pdf"]:
        files.append(to_rel_path(str(pdf_path)))
    if checks["exercises"]:
        files.append(to_rel_path(str(exercises_path)))
    if checks["overview_md"]:
        files.append(to_rel_path(str(overview_path)))

    audio_rel_dir = to_rel_path(str(audio_dir)) if audio_dir.exists() else ""
    audio_files_data = (
        [
            {
                "filename": filename,
                "url": f"/api/immersive/files/{audio_rel_dir}/{filename}"
                if audio_rel_dir
                else "",
                "duration_seconds": 0,
                "success": True,
            }
            for filename in audio_files
        ]
        if enable_audio
        else []
    )

    return {
        "ready": not missing,
        "checks": checks,
        "missing": missing,
        "optional_missing": optional_missing,
        "files": files,
        "num_frames": num_frames,
        "audio_files_count": len(audio_files_data),
        "audio_files": audio_files_data,
    }


def _audit_resume_chapters(
    session_id: str,
    course: CourseLayout,
    chapters: list[dict],
    chapters_state: list[dict],
    enable_audio: bool = False,
    enable_exercises: bool = True,
) -> tuple[list[dict], set[int], int]:
    """恢复生成前全量审计章节产物，并用真实磁盘状态覆盖旧 workspace。"""
    state_by_id = {
        item.get("chapter_id"): item
        for item in chapters_state
        if item.get("chapter_id") is not None
    }
    audited_state: list[dict] = []
    pending_ids: set[int] = set()

    for index, ch_info in enumerate(chapters):
        ch_id = ch_info.get("chapter_id", index + 1)
        title = ch_info.get("title", f"第{ch_id}章")
        old_item = state_by_id.get(ch_id, {})
        artifact_status = _chapter_artifact_status(
            course,
            ch_info,
            index,
            enable_audio=enable_audio,
            enable_exercises=enable_exercises,
        )
        status = "ready" if artifact_status["ready"] else "pending"
        if status != "ready":
            pending_ids.add(ch_id)
            logger.warning(
                "resume: 章节产物审计未通过 ch=%s missing=%s",
                ch_id,
                artifact_status["missing"],
            )

        block_ids = old_item.get("block_ids") or [f"chapter_{ch_id}_status"]
        audited_item = {
            **old_item,
            "chapter_id": ch_id,
            "title": title,
            "status": status,
            "block_ids": block_ids,
            "files": artifact_status["files"],
            "audio_enabled": enable_audio,
            "audio_files": artifact_status["audio_files"],
            "speaker_notes_count": len(artifact_status["audio_files"]),
            "artifact_status": artifact_status["checks"],
            "artifact_missing": artifact_status["missing"],
            "artifact_optional_missing": artifact_status["optional_missing"],
        }
        audited_state.append(audited_item)

        if status != "ready":
            upsert_canvas_block(
                session_id,
                {
                    "id": f"chapter_{ch_id}_status",
                    "type": "chapter_status",
                    "title": f"第{ch_id}章 {title}",
                    "status": "pending",
                    "chapter_id": ch_id,
                    "data": {
                        "stage": "pending",
                        "artifact_status": artifact_status["checks"],
                        "artifact_missing": artifact_status["missing"],
                        "artifact_optional_missing": artifact_status[
                            "optional_missing"
                        ],
                    },
                },
            )

    generated_chapters = len(
        [item for item in audited_state if item.get("status") == "ready"]
    )
    return audited_state, pending_ids, generated_chapters


def _difficulty_label(value: str) -> str:
    mapping = {
        "easy": "基础",
        "medium": "进阶",
        "hard": "挑战",
        "基础": "基础",
        "中等": "进阶",
        "困难": "挑战",
    }
    return mapping.get(str(value or "").strip(), str(value or "基础"))


def build_plan_markdown(topic: str, outline: dict) -> str:
    """将 Planner 产出的 outline 转成面向学习者的可读计划（精简版）。
    仅作为 LLM 个性化生成失败时的 fallback。
    """
    chapters = outline.get("chapters") or []
    lines = [f"# {topic} 学习计划", ""]

    # 章节路线（核心信息）
    lines.append("## 章节路线")
    for i, ch in enumerate(chapters, start=1):
        title = ch.get("title") or f"第{i}章"
        difficulty = _difficulty_label(ch.get("difficulty", "基础"))
        kps = ch.get("knowledge_points") or []
        kp_text = "、".join(kps[:4]) if kps else ""
        line = f"{i}. **{title}**（{difficulty}）"
        if kp_text:
            line += f"：{kp_text}"
        lines.append(line)

    # 首章引导（仅一句）
    if chapters:
        first_title = chapters[0].get("title") or "第一节"
        lines.extend(
            [
                "",
                f"> 先从「{first_title}」开始；PDF / 小测会在后台继续生成，不阻塞阅读。",
            ]
        )
    return "\n".join(lines)


def _clean_plan_markdown(raw: str, topic: str) -> str:
    """后处理 LLM 生成的学习建议 Markdown，确保格式质量。

    处理内容：
    1. 去除 ```markdown ``` 代码块包裹
    2. 去除其他语言标记的代码块包裹（如 ```text ```）
    3. 确保有一级标题
    4. 去除首尾多余空行
    """
    import re

    content = raw.strip()

    # 去除最外层的代码块包裹（支持 ```markdown、```md、```text、``` 等）
    # 匹配模式：开头的 ```xxx\n 和结尾的 \n```
    code_block_pattern = re.compile(
        r"^```(?:markdown|md|text|plain)?\s*\n(.*?)\n```\s*$",
        re.DOTALL,
    )
    match = code_block_pattern.match(content)
    if match:
        content = match.group(1).strip()

    # 如果整个内容仍然被代码块包裹（可能有多层），继续剥离
    while content.startswith("```") and content.endswith("```"):
        # 去掉第一行（```xxx）和最后一行（```）
        lines = content.split("\n")
        if len(lines) >= 3:
            content = "\n".join(lines[1:-1]).strip()
        else:
            break

    # 确保有一级标题
    if not content.startswith("#"):
        content = f"# {topic} 学习建议\n\n{content}"

    # 确保标题后有空行
    lines = content.split("\n")
    if len(lines) >= 2 and lines[0].startswith("#") and lines[1].strip() != "":
        lines.insert(1, "")
        content = "\n".join(lines)

    return content


async def build_personalized_plan(
    topic: str,
    outline: dict,
    user_id: str,
    profile_content: str = "",
) -> str:
    """结合用户画像和课程大纲，调用 LLM 生成个性化学习建议。

    与大纲不同，学习建议侧重于：
    - 根据用户背景给出学习策略
    - 根据已有知识基础推荐学习重点/可跳过的内容
    - 给出时间分配建议
    - 提供学习方法建议

    如果 LLM 调用失败，fallback 到 build_plan_markdown。
    """

    # 构建大纲摘要（供 LLM 参考，不需要全部细节）
    chapters = outline.get("chapters") or []
    outline_summary_lines = []
    for i, ch in enumerate(chapters, start=1):
        title = ch.get("title") or f"第{i}章"
        difficulty = ch.get("difficulty", "基础")
        kps = ch.get("knowledge_points") or []
        kp_text = "、".join(kps[:6]) if kps else "无"
        outline_summary_lines.append(
            f"{i}. {title}（难度：{difficulty}）- 知识点：{kp_text}"
        )
    outline_summary = "\n".join(outline_summary_lines)

    # 构建用户画像上下文
    profile_section = ""
    if profile_content and profile_content.strip():
        profile_section = f"""
## 用户画像
{profile_content.strip()}
"""
    else:
        profile_section = """
## 用户画像
暂无用户画像信息（新用户）。请给出通用的学习建议。
"""

    system_prompt = """你是一位经验丰富的学习顾问，擅长根据学生的背景和目标制定个性化学习策略。
你的任务是根据课程大纲和用户画像，生成一份个性化的学习建议。

要求：
1. 直接输出 Markdown 正文，**禁止**用 ```markdown ``` 代码块包裹内容
2. 内容要与大纲有明显差异化——大纲展示"学什么"，你要告诉学生"怎么学"
3. 根据用户的已有知识基础，指出哪些章节可以快速浏览、哪些需要重点攻克
4. 给出合理的时间分配建议（如每章建议花多少时间）
5. 提供具体的学习方法建议（如先看PDF再做题、还是边看边练等）
6. 如果用户有学习历史，参考其掌握度给出针对性建议
7. 语气亲切自然，像一位学长/导师在给建议
8. 总长度控制在 300-600 字之间，不要太长
9. 不要重复罗列大纲中已有的章节标题和知识点列表

格式规范（非常重要，请严格遵守）：
- 第一行必须是 `# 课程名 学习建议` 格式的一级标题
- 开头用 1-2 句话点明这门课对用户的价值和整体学习策略
- 用 `**加粗小标题：**` 分隔不同建议板块（如"建议重点分层："、"时间分配建议："、"具体学法："、"特别建议："）
- 列表项用 `-` 无序列表，步骤用 `1. 2. 3.` 有序列表
- 重点内容用 `**加粗**` 标注
- 段落之间用空行分隔
- 不要使用二级标题(##)，用加粗文本代替小标题
- 不要使用表格"""

    user_prompt = f"""# 课程主题：{topic}

## 课程大纲（共 {len(chapters)} 章）
{outline_summary}
{profile_section}
请为这位学习者生成个性化的学习建议。"""

    try:
        llm = get_llm(user_id)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = await llm.async_think(
            messages, config={"temperature": 0.7, "max_tokens": 1024}
        )

        if response and response.content and not response.is_error:
            content = _clean_plan_markdown(response.content, topic)
            return content
        else:
            logger.warning("LLM 生成个性化学习计划返回空或错误，使用 fallback")
            return build_plan_markdown(topic, outline)
    except Exception as e:
        logger.warning("LLM 生成个性化学习计划失败: %s，使用 fallback", e)
        return build_plan_markdown(topic, outline)


def _safe_load_research(research_path: "Path") -> dict:
    """安全加载 research.json，重点保护 LaTeX 反斜杠序列。

    LLM 写出的 JSON 经常把 LaTeX 命令直接塞进字符串，比如
    ``"...单个能量子满足 $\\epsilon=h\\nu$..."``，这里的 ``\\nu`` 在原始字节
    里其实只有一个反斜杠（``\\n``），结果：
      - 严格 JSON 视为非法转义（如 ``\\f``、``\\v``）→ 直接 loads 失败；
      - 即便解析成功，``\\nu`` 中的 ``\\n`` 也会被 JSON 解释成换行符
        → ``\\nu`` 变 ``\n + u``，``\\frac`` 变 ``\f + rac``，公式被吞。

    因此本函数采用更激进的策略：**任何 ``\\<字母>`` 序列在 loads 之前都先翻倍**，
    这样无论 JSON 视它为合法转义还是非法转义，最终解析出的字符串里都会保留
    完整的 ``\\nu`` / ``\\frac`` 字面，给前端 KaTeX 正常渲染。
    """
    import json as _json
    import re as _re

    if not research_path.exists():
        return {}

    raw = research_path.read_text(encoding="utf-8")

    # 只在"公式分隔符内部"翻倍反斜杠，避免把段落里的 JSON 换行 \n / 制表符 \t
    # 误判成 LaTeX 命令而翻倍——例如 LLM 写的 `$$\nE_n=...`，本意是 `$$` 后接
    # 换行 + `E_n=...`，旧实现会把 `\nE` 当成 LaTeX 命令翻倍成 `\\nE`，结果
    # JSON 解析后字面字符 `\nE_n` 残留到 markdown 里，前端 KaTeX 报错。
    #
    # 公式分隔符列举：$$...$$（多行）、$...$（单行）、\[...\]、\(...\)。
    _MATH_SPAN = _re.compile(
        r"(?P<dd>\$\$[\s\S]+?\$\$)"
        r"|(?P<sd>\$[^\$\n]+?\$)"
        r"|(?P<br>\\\[[\s\S]+?\\\])"
        r"|(?P<pa>\\\([\s\S]+?\\\))"
    )

    def _protect_latex(s: str) -> str:
        # 在公式 span 内，把"孤立的单反斜杠 + LaTeX 命令/标点"翻倍。
        #
        # 难点：raw 字节序列里 ``\\`` 与 ``\\\\`` 都可能合法存在，必须精确
        # 区分"当前 ``\`` 是不是已成对反斜杠的一部分"。Python 正则的
        # ``(?<!\\)`` 只能往前看 1 字节，无法判断成对。因此改用**逐字节
        # 状态机**：扫描时数前面连续反斜杠的奇偶——奇数表示这是孤立 ``\``，
        # 后面紧跟 LaTeX 命令或标点时需要翻倍；偶数表示已成对（已经是合法
        # 的 ``\\`` raw 对，JSON 解码后是单 ``\``，即 LaTeX 行分隔/字面 ``\\``），
        # 保持原样。
        #
        # JSON 解码下，``\\b`` ``\\f`` ``\\n`` ``\\r`` ``\\t`` ``\\u``
        # 是合法转义对（→ 控制字符），但在公式 span 内几乎一定是 LaTeX 命令
        # 前缀（``\beta \frac \nu \rho \tau \upsilon``）：状态机把它们当
        # 成"奇数 ``\`` + 字母"处理——即翻倍——能正确恢复 LaTeX 命令。

        def _double_backslashes_in(span: str) -> str:
            # 检测 span 内 \begin{多行环境}...\end{...} 区间。这些环境里
            # 的 ``\\`` 几乎一定是 LaTeX 行分隔（cases/aligned/array/matrix
            # 等），LLM 常把 raw 写成 2 反斜杠（不够，应 4）。需要在区间内
            # 对 ``\\`` + 字母做"再翻倍"补救。
            #
            # 普通 ``$...$`` 行内公式里的 ``\\psi`` ``\\rangle`` 等是 LLM
            # 写对的 LaTeX 命令前缀，绝不能翻倍。
            MULTI_LINE_ENVS = (
                "cases",
                "aligned",
                "align",
                "gather",
                "gathered",
                "array",
                "matrix",
                "pmatrix",
                "bmatrix",
                "vmatrix",
                "Bmatrix",
                "Vmatrix",
                "split",
                "multline",
                "eqnarray",
            )
            ml_intervals = []  # list of (begin_pos, end_pos, has_newline_decor)
            # 用宽松正则找出 \begin{<env>}…\end{<env>}，无论 raw 反斜杠数
            for bm in _re.finditer(
                r"\\+begin\{(" + "|".join(MULTI_LINE_ENVS) + r")\}",
                span,
            ):
                env = bm.group(1)
                em = _re.search(
                    r"\\+end\{" + env + r"\}",
                    span[bm.end() :],
                )
                if em:
                    abs_end = bm.end() + em.end()
                    region = span[bm.start() : abs_end]
                    # 检测 LLM 是否用 ``\\n`` 做行装饰：raw 里出现"两个反斜杠
                    # + n + 后非字母"就是 JSON 转义换行装饰，"\\ + 字母" 在
                    # 这种 region 里几乎一定是 JSON 转义而非 LaTeX 行分隔。
                    has_newline_decor = bool(_re.search(r"\\\\n(?![A-Za-z])", region))
                    ml_intervals.append((bm.start(), abs_end, has_newline_decor))

            def in_multiline(pos: int) -> bool:
                return any(s <= pos < e for s, e, _ in ml_intervals)

            def multiline_has_newline_decor(pos: int) -> bool:
                for s, e, has in ml_intervals:
                    if s <= pos < e:
                        return has
                return False

            out = []
            i = 0
            n = len(span)
            while i < n:
                c = span[i]
                if c != "\\":
                    out.append(c)
                    i += 1
                    continue
                # 数当前位置开始的连续反斜杠数量
                j = i
                while j < n and span[j] == "\\":
                    j += 1
                run = j - i  # 连续反斜杠数量
                # 后接字符（无则 None）
                nxt = span[j] if j < n else None
                # LaTeX 命令/标点：字母、{ } | , ; : ! # & _ 空格、( ) [ ]
                # 加 () [] 是因为 LaTeX 行内/块公式定界符 \( \) \[ \] 在 JSON
                # 中也是非法转义，必须翻倍。
                is_latex_follow = nxt is not None and (
                    nxt.isalpha() or nxt in "{}|,;:!#&_ ()[]"
                )
                # JSON 合法单字符转义起头：``\n`` ``\r`` ``\t`` ``\b`` ``\f``
                # ``\u``。LaTeX 中虽然 ``\b`` ``\t`` 单字母命令存在但极少用，
                # 常用的都是 ``\nu \neq \nabla \tau \theta \beta \frac \rho``
                # 等多字母——所以"奇数反斜杠 + 单字符 [nrtbfu] + 后面再无字母"
                # 几乎一定是 LLM 写的 JSON 转义换行/制表符等。绝不能翻倍——
                # 翻倍会把 ``\n``(换行) 变成字面 ``\\n``（公式里的红色 ``\n``）。
                # 检测方式：看 nxt 是不是 [nrtbfu] 且 nxt+1 不是字母（即
                # ``\nu`` 这种连续字母 LaTeX 命令不在此列）。
                is_json_short_escape = (
                    run % 2 == 1
                    and nxt in ("n", "r", "t", "b", "f", "u")
                    and (j + 1 >= n or not span[j + 1].isalpha())
                )
                # 后接是否字母/数字（仅在多行环境内用于检测 LLM 写错的
                # LaTeX 行分隔 ``\\`` raw 写成 2 反斜杠的情况）
                # 数字也算：pmatrix 内 ``0&1\\1&0`` 这种 raw，1 是数字。
                nxt_is_alnum = nxt is not None and (nxt.isalpha() or nxt.isdigit())
                # 但 ``\\begin{...}`` ``\\end{...}`` 是 LaTeX 命令本身（前
                # 导双反斜杠 raw 是 LLM 写对的命令前缀），绝不能再翻倍。
                is_begin_end = span[j : j + 5] == "begin" or span[j : j + 3] == "end"

                if run % 2 == 1 and is_latex_follow and not is_json_short_escape:
                    # 奇数反斜杠 + LaTeX 命令/标点（且非 JSON 合法单字符转义）
                    # → 翻倍最后一个反斜杠
                    out.append("\\" * (run + 1))
                elif (
                    run == 2
                    and nxt_is_alnum
                    and not is_begin_end
                    and in_multiline(i)
                    and not multiline_has_newline_decor(i)
                ):
                    # 多行环境内（且非 begin/end）的双反斜杠 + 字母/数字：
                    # LLM 写错的 LaTeX 行分隔（raw 应 4 反斜杠才对，写 2
                    # 不够），补成 4 让 JSON 解码后得到 ``\\``（合法 LaTeX
                    # 行分隔）。
                    #
                    # 但若该多行区间内已有 ``\\n`` JSON 换行装饰（说明 LLM
                    # 用真换行/字面 \\n 来分行），就不应再把 ``\\`` + 字母
                    # 当成行分隔——那时它几乎一定是 JSON 转义，翻倍反而会
                    # 把 ``\n`` 字面化（残留红字）。
                    out.append("\\" * 4)
                else:
                    # 偶数（已成对）或后面不是 LaTeX 字符 → 原样保留
                    out.append("\\" * run)
                i = j
            return "".join(out)

        def _repl(m: "_re.Match") -> str:
            return _double_backslashes_in(m.group(0))

        return _MATH_SPAN.sub(_repl, s)

    # 第一次尝试：保护 LaTeX 反斜杠后解析（首选，最干净）
    try:
        return _json.loads(_protect_latex(raw))
    except Exception:
        pass

    # 第二次尝试：再叠加"非法反斜杠通配翻倍"，覆盖偶发的 \空格 / \中文 等
    try:
        protected = _protect_latex(raw)
        # 此时仍可能存在 \X (X 非 ["\\/bfnrtu] 也非字母) 的非法转义，再翻一次
        fixed = _re.sub(r'\\(?!["\\/bfnrtu]|[A-Za-z])', r"\\\\", protected)
        return _json.loads(fixed)
    except Exception:
        pass

    # 第三次尝试：先公式保护，再用最宽松的"翻倍所有非法反斜杠"
    # 注意必须先 _protect_latex，否则公式里 \frac \beta \theta \tau \rho 这些
    # 以 JSON 合法转义首字母（\f \b \t \r）开头的命令会被解析为 form-feed/退格/
    # 制表符/CR，公式被破坏。
    try:
        protected = _protect_latex(raw)
        fixed = _re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", protected)
        return _json.loads(fixed)
    except Exception:
        pass

    # 兜底：从原文里只抠 sources 字段（title + url），其它一律放弃
    result = {}
    try:
        m = _re.search(r'"sources"\s*:\s*(\[.*?\])', raw, flags=_re.DOTALL)
        if m:
            try:
                result["sources"] = _json.loads(m.group(1))
            except Exception:
                pairs = _re.findall(
                    r'\{\s*"title"\s*:\s*"([^"]+)"\s*,\s*"url"\s*:\s*"([^"]+)"',
                    m.group(1),
                )
                result["sources"] = [{"title": t, "url": u} for t, u in pairs]
    except Exception:
        pass
    return result


def _normalize_math_in_text(text: str) -> str:
    """对从 raw_text 抽出的 markdown 做一些防御性规范化。

    - 把 ``\\[ ... \\]`` 转为 ``$$ ... $$``、``\\( ... \\)`` 转为 ``$ ... $``，
      让前端老的 marked 即使没识别到 \\[\\] 也能渲染；
    - 把孤立成行的 ``$$ ... $$`` 前后强制留空行（避免被 marked 视为段落内文本）。
    """
    import re as _re

    if not text:
        return text

    # \[ ... \]  →  $$ ... $$
    text = _re.sub(
        r"\\\[([\s\S]+?)\\\]",
        lambda m: "\n$$" + m.group(1).strip() + "$$\n",
        text,
    )
    # \( ... \)  →  $ ... $
    text = _re.sub(r"\\\((.+?)\\\)", r"$\1$", text)

    # 清理公式 span 内字面 ``\n``/``\r``/``\t`` 残留，但 **必须** 严格限定
    # 在"后面紧跟另一个反斜杠"的场景，否则会误伤 LaTeX 命令：
    #   - ``\rho`` ``\rangle`` ``\right`` ``\rfloor`` ``\rceil``
    #   - ``\theta`` ``\times`` ``\top`` ``\to`` ``\tan`` ``\tau`` ``\text``
    #     ``\triangle`` ``\tilde``
    #   - ``\nabla`` ``\nu`` ``\neq`` ``\ne`` ``\not`` ``\notin`` ``\ni``
    # 这些命令的首字母都是 n/r/t —— 一旦把"\n/\r/\t + 字母"也清理，命令就被
    # 整段吞掉（``\rho`` → ``ho``、``\times`` → ``imes``、``\top`` → ``op`` 等）。
    #
    # 因此本步只删除 ``\n\X`` ``\r\X`` ``\t\X`` 这种"两个反斜杠紧贴"形态——
    # 这种几乎一定是 LLM 写错的 JSON 换行后又紧跟下一条 LaTeX 命令所致。
    # 仍然保留前导 ``\X``，让命令本身完整。
    def _clean_span(m: "_re.Match") -> str:
        s = m.group(0)
        multiline_env_re = (
            r"\\begin\{(?:cases|aligned|align|gather|gathered|array|matrix|pmatrix|"
            r"bmatrix|vmatrix|Bmatrix|Vmatrix|split|multline|eqnarray)\}"
        )
        has_multiline_env = bool(_re.search(multiline_env_re, s))
        is_block_math = s.startswith("$$") and s.endswith("$$")
        if has_multiline_env:
            # 多行环境里，LLM 有时把 LaTeX 行分隔 ``\\`` 写成了行尾单 ``\``。
            # 只在真实换行前修复，避免误伤 ``\nu``、``\neq`` 等正常命令。
            s = _re.sub(
                r"(?<!\\)\\([ \t]*\n[ \t]*)(?=(?:\\(?:vdots|cdots|dots|begin|end)\b|[A-Za-z0-9]))",
                r"\\\\\1",
                s,
            )
            # 多行环境里，``\\n`` 经常表示"行分隔 + JSON 换行残留 n"，
            # 例如 ``\\na_{m1}`` / ``\\n a_{m1}`` 应恢复为 ``\\\na_{m1}``。
            # 限定后续形态为普通变量/数字行首，保护 ``\\\nabla`` 这类命令。
            s = _re.sub(
                r"(\\\\)n[ \t]*(?=(?:[A-Za-z](?:[_\{]|\d)|[0-9]))",
                r"\1\n",
                s,
            )
            if is_block_math:
                # 块级多行环境若被压成一行，Markdown/KaTeX 边界容易把
                # ``\\vdots\\a_{m1}`` 解析成同一行或残留 ``n``。这里统一展开：
                #   $$\begin{cases}a=...\\\vdots\\a_m=...\end{cases}$$
                # 变成 $$、\begin、每个行分隔、\end 各自占稳定边界。
                s = _re.sub(r"(\$\$)[ \t]*(\\begin\{[a-zA-Z]+\})[ \t]*", r"\1\n\2\n", s)
                s = _re.sub(r"[ \t]*(\\end\{[a-zA-Z]+\})[ \t]*(\$\$)", r"\n\1\n\2", s)
                s = _re.sub(
                    r"(\\\\)(?=(?:\\[A-Za-z]+\b|[A-Za-z0-9]))",
                    r"\1\n",
                    s,
                )
                s = _re.sub(
                    r"(?m)^([ \t]*)(vdots|cdots|dots)([ \t]*\\\\)",
                    r"\1\\\2\3",
                    s,
                )
                s = _re.sub(r"\n{2,}(?=\\end\{[a-zA-Z]+\})", "\n", s)
        # ① ``\n\X`` ``\r\X`` ``\t\X`` 紧贴下一条 LaTeX 命令——LLM 写错的
        #    JSON 换行残留。删除前导 ``\n``/``\r``/``\t``，保留后续命令。
        s = _re.sub(r"(?<!\\)\\[nrt](?=\\)", "", s)
        # ② 公式起始 ``$$\n``/``$\n``——LLM 在 raw 里写公式时把段首换行
        #    误用 JSON 转义 ``\n`` 嵌入。**严格** 要求 ``\n`` 后不接字母，
        #    否则会把 ``\rho \nu \tau \theta`` 等以 r/n/t 开头的 LaTeX 命令
        #    首字母吃掉（``$$\rho=`` 误读为 ``$$\r ho=`` 把 ``\r`` 当噪声删）。
        s = _re.sub(r"(\$\$|\$)\\[nrt](?![A-Za-z])", r"\1", s)
        # ③ 公式末尾 ``\n$$``/``\n$``——同 ②，严格要求 ``\n`` 前不在字母旁
        s = _re.sub(r"(?<![A-Za-z])\\[nrt](\$\$|\$)", r"\1", s)
        # ④ ``\n``/``\r``/``\t`` + 单字母 + 非字母——cases 等多行环境内
        #    LLM 段首装饰被翻倍后的字面残留（如 ``\na_{11}`` ``\nx_1+`` 等）。
        #    严格要求"字母后必须是非字母"，避免误伤 ``\nabla \neq \nu``
        #    ``\theta \times \top \tau`` 这种连续字母 LaTeX 命令。
        s = _re.sub(
            r"(?<!\\)\\[nrt](?=[A-Za-z][^A-Za-z])",
            "",
            s,
        )
        # ⑤ 公式 span 内紧跟在 ``\begin{<env>}`` 之后的 ``\n``/``\r``/``\t``
        #    严格要求后不接字母（避免 ``\begin{cases}\rho`` 被误删 ``\r``）
        s = _re.sub(
            r"(\\begin\{[a-zA-Z]+\})\\[nrt](?![A-Za-z])",
            r"\1",
            s,
        )
        # ⑥ 公式 span 内紧贴在 ``\end{<env>}`` 之前的 ``\n``/``\r``/``\t``
        s = _re.sub(
            r"(?<![A-Za-z])\\[nrt](\\end\{[a-zA-Z]+\})",
            r"\1",
            s,
        )
        # ⑦ LaTeX 行分隔 ``\\`` 后接的 ``\n``/``\r``/``\t`` 装饰残留
        #    严格要求其后不接字母（保护 ``\\\rho`` 这种 LaTeX 行分隔后命令）
        s = _re.sub(
            r"(\\\\)\\[nrt](?![A-Za-z])",
            r"\1",
            s,
        )
        return s

    # 块级 $$..$$
    text = _re.sub(r"\$\$[\s\S]+?\$\$", _clean_span, text)
    # 行内 $..$
    text = _re.sub(r"\$[^\$\n]+?\$", _clean_span, text)

    # 多余空行收敛到 2 行
    text = _re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _normalize_research_raw_text_file(research_path: "Path") -> bool:
    """规范化 research.json 里的 raw_text，并在内容变化时回写源缓存。"""
    research = _safe_load_research(research_path)
    raw_text = research.get("raw_text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        return False

    normalized = _normalize_math_in_text(raw_text)
    if normalized == raw_text:
        return False

    research["raw_text"] = normalized
    research_path.write_text(
        json.dumps(research, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def _build_chapter_summary_md(
    ch_title: str,
    ch_info: dict,
    research_path: "Path",
) -> str:
    """基于 research.json 生成章节预习手册 Markdown（不依赖 TeX）。

    定位：在 PDF 讲义生成之前就推送给用户阅读的"预习文档"，
    帮助用户快速了解本章核心内容，为后续 PDF 讲义的深入学习做铺垫。

    内容布局：
      ## 📖 {章节名} — 预习手册
      ### 🎯 本章学习目标      ← outline.description + knowledge_points
      ### 📝 核心内容          ← research.raw_text 全文（带公式）
      ### 🔗 延伸阅读          ← research.sources（带超链接）
      ### 💡 预习提示          ← 基于知识点生成的学习建议

    LaTeX 公式保护由 _safe_load_research 完成，这里只做 markdown 防御性规范化。
    """

    lines = [f"## 📖 {ch_title} — 预习手册", ""]

    # 1) 本章学习目标
    kps = ch_info.get("knowledge_points", []) or []
    desc = (ch_info.get("description") or "").strip()
    if kps or desc:
        lines.append("### 🎯 本章学习目标")
        if desc:
            lines.append(f"> {desc}")
            lines.append("")
        if kps:
            lines.append("学完本章，你应该能够理解以下知识点：")
            lines.append("")
            for idx, kp in enumerate(kps, 1):
                lines.append(f"{idx}. {kp}")
            lines.append("")

    # 2) 核心内容（来自 research.raw_text，最具信息量的一段）
    research = _safe_load_research(research_path)
    raw_text = (research.get("raw_text") or "").strip()
    if raw_text:
        normalized = _normalize_math_in_text(raw_text)
        lines.append("### 📝 核心内容")
        lines.append(normalized)
        lines.append("")

    # 3) 延伸阅读（参考来源）
    sources = research.get("sources") or []
    if sources:
        lines.append("### 🔗 延伸阅读")
        for src in sources[:6]:
            title = (src.get("title") or "").strip()
            url = (src.get("url") or "").strip()
            summary = (src.get("summary") or "").strip()
            if title and url:
                lines.append(f"- [{title}]({url})")
                if summary:
                    lines.append(f"  {summary}")
            elif title:
                lines.append(f"- {title}")
        lines.append("")

    # 4) 预习提示
    if kps:
        lines.append("### 💡 预习提示")
        lines.append("阅读以上内容时，建议你带着以下问题思考：")
        lines.append("")
        # 从知识点中提取前 3 个作为思考问题
        for kp in kps[:3]:
            lines.append(f"- 什么是「{kp}」？它解决了什么问题？")
        lines.append("")
        lines.append("---")
        lines.append("*📑 详细的图文讲义（PDF）正在生成中，稍后将自动推送给你。*")
        lines.append("")

    # 6) 路标提示（仅当没有 raw_text 时才提示去看 PDF；有内容时不必强调）
    if not raw_text:
        lines.append(
            "> 完整推导、公式与配图请打开本章 PDF 查看；本页用于快速建立全局印象。"
        )

    if len(lines) <= 3:
        return ""

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# 并行 Research 辅助函数
# ─────────────────────────────────────────────────────────────────────


async def _run_single_chapter_research(
    agent: "ReActAgent",
    topic: str,
    ch_id: int,
    ch_title: str,
    ch_info: dict,
    research_path: "Path",
) -> dict:
    """并发执行单章 Research，返回收集到的 SSE 事件列表和结果信息。

    不直接 yield SSE 事件，而是收集到列表中，供调用方统一推送。
    """
    events = []
    success = False

    try:
        researcher_prompt = (
            f"为课程「{topic}」第 {ch_id} 章「{ch_title}」检索学习资料。\n"
            f"知识点：{', '.join(ch_info.get('knowledge_points', []))}\n"
            f"搜索关键词：{', '.join(ch_info.get('search_keywords', []))}\n"
            f"将结果写入：{research_path}"
        )

        async for ev in stream_agent_events(
            agent,
            researcher_prompt,
            "researcher",
            start_msg=f"开始检索第{ch_id}章资料",
            finish_msg="检索完成",
        ):
            events.append(ev)

        success = research_path.exists() and research_path.stat().st_size > 50
        logger.info(
            "并行 Researcher 完成: 第%d章 %s (success=%s)", ch_id, ch_title, success
        )

        # 规范化 research.raw_text
        try:
            if _normalize_research_raw_text_file(research_path):
                logger.info(
                    "并行已规范化 research.raw_text: 第%d章 %s", ch_id, ch_title
                )
        except Exception as exc:
            logger.warning("并行规范化 research.raw_text 失败 ch=%s: %s", ch_id, exc)

    except Exception as exc:
        logger.error("并行 Researcher 异常: 第%d章 %s: %s", ch_id, ch_title, exc)

    return {
        "ch_id": ch_id,
        "ch_title": ch_title,
        "ch_info": ch_info,
        "events": events,
        "success": success,
        "research_path": research_path,
    }


def _build_researcher_agent(layout: "UserDataLayout", user_id: str) -> "ReActAgent":
    """为并行 research 构建独立的 researcher agent 实例。

    每个并发任务需要独立的 agent 实例，避免内部 history 冲突。
    """
    tavily_key = get_setting(user_id, "tavily_api_key") or os.getenv(
        "TAVILY_API_KEY", ""
    )

    return ReActAgent(
        llm=get_llm(user_id),
        context_builder=SimpleContextBuilder(
            "你是信息检索与整理助手。根据章节信息检索资料，整理为 JSON 写入指定路径。\n\n"
            "**JSON 输出格式**：\n"
            '{"chapter_id": N, "chapter_title": "...",\n'
            '  "sources": [{"title": "标题", "url": "https://...", "summary": "一句话摘要"}],\n'
            '  "raw_text": "整合后的 Markdown 正文（不超过 2000 字）"}\n\n'
            "**raw_text 必须遵守的格式规范**（前端会以 Markdown 直接渲染，质量直接影响用户体验）：\n"
            "1. 必须使用 Markdown 结构：用 `### 小节标题` 分块，每块下用短段落 + 列表，避免出现整段大段文字。\n"
            "2. 严禁出现裸 URL；若需引用网址，**必须**写成 `[显示文本](https://...)` 的 markdown 链接形式。\n"
            "3. 数学公式使用 LaTeX：行内用 `$...$`，独立公式用 `$$...$$`。\n"
            "4. 重要术语和关键概念用 `**加粗**`，对易混淆点可用 `> 引用块` 提醒。\n"
            "5. 不要把 sources 里的链接列表再原样附在 raw_text 末尾（前端会单独展示）。\n"
            "6. 内容要求循序渐进：先给定义/直观解释，再给关键性质/算法步骤，最后给注意事项或常见误区。\n"
            "7. 优先使用中文资料；如果只有英文，请翻译为中文表达。\n\n"
            "**工作流程**：\n"
            "1. 用 search 工具检索 2-4 条权威资料\n"
            "2. （可选）对最相关的 1-2 条用 web_fetch 抓取详细内容\n"
            "3. 整合为符合上述规范的 raw_text，并将 sources 列表填好\n"
            "4. 用 write_file 写入指定的 research.json 路径"
        ),
        tool_registry=ToolRegistry(
            [
                TavilySearch(api_key=tavily_key),
                ArxivSearch(),
                WebFetch(),
                WriteFileTool(),
            ]
        ),
        max_steps=8,
    )


async def _parallel_research_all_chapters(
    topic: str,
    chapters: list,
    course: "CourseLayout",
    layout: "UserDataLayout",
    user_id: str,
    max_concurrency: int = 0,
) -> list:
    """并发执行所有章节的 Research，返回每章的结果列表。

    max_concurrency=0 表示不限制并发数（即所有章节同时执行）。
    """
    import asyncio

    # max_concurrency <= 0 表示不限制，设为章节总数
    effective_concurrency = max_concurrency if max_concurrency > 0 else len(chapters)
    semaphore = asyncio.Semaphore(effective_concurrency)

    async def _limited_research(agent, topic, ch_id, ch_title, ch_info, research_path):
        async with semaphore:
            return await _run_single_chapter_research(
                agent, topic, ch_id, ch_title, ch_info, research_path
            )

    tasks = []
    for i, ch_info in enumerate(chapters):
        ch_id = ch_info.get("chapter_id", i + 1)
        ch_title = ch_info.get("title", f"第{ch_id}章")
        research_path = course.chapter_dir(ch_id) / "research.json"
        course.chapter_dir(ch_id).mkdir(parents=True, exist_ok=True)

        # 每章创建独立的 researcher agent 实例
        researcher_agent = _build_researcher_agent(layout, user_id)

        tasks.append(
            _limited_research(
                researcher_agent, topic, ch_id, ch_title, ch_info, research_path
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 处理异常情况
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            ch_info = chapters[i]
            ch_id = ch_info.get("chapter_id", i + 1)
            ch_title = ch_info.get("title", f"第{ch_id}章")
            logger.error("并行 research 异常 ch=%s: %s", ch_id, result)
            final_results.append(
                {
                    "ch_id": ch_id,
                    "ch_title": ch_title,
                    "ch_info": ch_info,
                    "events": [],
                    "success": False,
                    "research_path": course.chapter_dir(ch_id) / "research.json",
                }
            )
        else:
            final_results.append(result)

    return final_results


async def immersive_generate(
    topic: str,
    user_id: str,
    user_profile: str = "",
    enable_audio: bool = False,
    enable_exercises: bool = True,
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
        logger.info(
            "沉浸式学习会话: %s (topic=%s, enable_audio=%s)",
            session_id,
            topic,
            enable_audio,
        )

        layout = UserDataLayout(root=DOCUMENTS_DIR, user_id=user_id)
        layout.ensure_dirs()
        if user_profile:
            layout.profile_file.write_text(user_profile, encoding="utf-8")
        elif (
            not layout.profile_file.exists()
            or not layout.profile_file.read_text(encoding="utf-8").strip()
        ):
            # 前端未传 user_profile 且 profile.md 为空时，尝试从 DB 同步
            try:
                from services import UserService

                user_info = UserService().get_user(user_id)
                if user_info and hasattr(user_info, "about") and user_info.about:
                    UserService()._sync_about_to_profile(user_id, user_info.about)
            except Exception as e:
                logger.warning("generate 时自动同步 profile 失败: %s", e)

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

        # 读取用户画像用于生成个性化学习建议（带 fallback 到旧全局文件）
        profile_content = ""
        try:
            if layout.profile_file.exists():
                profile_content = layout.profile_file.read_text(
                    encoding="utf-8"
                ).strip()
            if not profile_content and user_id:
                # fallback: 旧的全局 profile.md（迁移兼容）
                legacy_profile = layout.profile_dir / "profile.md"
                if legacy_profile.exists() and legacy_profile != layout.profile_file:
                    profile_content = legacy_profile.read_text(encoding="utf-8").strip()
        except Exception:
            pass

        yield sse_event(
            "progress", stage="plan", pct=12, message="📝 正在生成个性化学习建议..."
        )
        plan_md = await build_personalized_plan(
            topic, outline, user_id, profile_content
        )
        plan_path = course.course_dir / "plan.md"
        plan_path.write_text(plan_md, encoding="utf-8")
        rel_plan_path = to_rel_path(str(plan_path))

        outline_block = {
            "id": "outline",
            "type": "outline",
            "title": "学习大纲",
            "status": "ready",
            "data": {
                "outline": outline,
                "outline_path": to_rel_path(str(outline_path)),
            },
        }
        plan_block = {
            "id": "plan_md",
            "type": "md",
            "title": f"{topic} 个性化学习建议",
            "status": "ready",
            "data": {
                "subtype": "personalized_plan",
                "markdown": plan_md,
                "markdown_path": rel_plan_path,
                "estimated_chapters": total_ch,
            },
        }
        workspace_patch = {
            "topic": topic,
            "enable_audio": enable_audio,
            "enable_exercises": enable_exercises,
            "planned_chapters": total_ch,
            "generated_chapters": 0,
            "current_chapter_id": chapters[0].get("chapter_id", 1)
            if chapters
            else None,
            "chapters": [
                {
                    "chapter_id": ch.get("chapter_id", idx + 1),
                    "title": ch.get("title", f"第{idx + 1}章"),
                    "status": "pending",
                    "block_ids": [],
                }
                for idx, ch in enumerate(chapters)
            ],
        }
        next_actions = [
            {"type": "start_learning", "label": "查看学习建议"},
            {"type": "continue_generation", "label": "后台继续生成第一章"},
        ]
        upsert_canvas_block(
            session_id,
            outline_block,
            current=True,
            stage="planned",
            next_actions=next_actions,
            workspace_patch=workspace_patch,
        )
        upsert_canvas_block(session_id, plan_block, current=True, stage="planned")
        append_session_file(session_id, rel_plan_path, f"{topic} 个性化学习建议", "md")

        yield sse_event(
            "progress",
            stage="planner",
            pct=15,
            message=f"✅ 大纲完成，共 {total_ch} 章",
        )
        yield sse_event("outline", data=outline)
        yield sse_event(
            "workspace_update",
            event="block_created",
            session_id=session_id,
            block=outline_block,
            next_actions=next_actions,
        )
        yield sse_event(
            "workspace_update",
            event="block_created",
            session_id=session_id,
            block=plan_block,
            next_actions=next_actions,
        )

        # ── 2. 并行 Research + 预习手册 ─────────────────────

        tts_llm = get_llm(user_id) if enable_audio else None
        chapter_results = []
        all_files_for_session = []
        pct_per_chapter = 75.0 / max(total_ch, 1)  # 15% ~ 90%

        # ── 2a. 并发执行所有章节的 Research ──────────────────────
        yield sse_event(
            "progress",
            stage="researcher",
            pct=16,
            message=f"🔍 并行检索所有章节资料（共 {total_ch} 章）...",
        )

        research_results = await _parallel_research_all_chapters(
            topic=topic,
            chapters=chapters,
            course=course,
            layout=layout,
            user_id=user_id,
            max_concurrency=total_ch,
        )

        # ── 2a+. 逐章推送预习手册（Research 全部完成后统一推送）──
        # 按章节顺序推送，让前端按序展示
        research_pct_done = 15 + int(pct_per_chapter * total_ch * 0.25)
        yield sse_event(
            "progress",
            stage="researcher",
            pct=min(research_pct_done, 40),
            message=f"✅ 全部 {total_ch} 章资料检索完成，正在生成预习手册...",
        )

        for i, res in enumerate(research_results):
            ch_id = res["ch_id"]
            ch_title = res["ch_title"]
            ch_info = res["ch_info"]
            research_path = res["research_path"]

            # 生成预习手册 Markdown
            chapter_md_content = _build_chapter_summary_md(
                ch_title, ch_info, research_path
            )
            chapter_md_rel = ""
            chapter_md_path = None
            if chapter_md_content:
                chapter_md_path = (
                    course.chapter_dir(ch_id) / f"chapter_{ch_id:02d}_overview.md"
                )
                try:
                    chapter_md_path.parent.mkdir(parents=True, exist_ok=True)
                    chapter_md_path.write_text(chapter_md_content, encoding="utf-8")
                    chapter_md_rel = to_rel_path(str(chapter_md_path))
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning(
                        "预习手册 markdown 落盘失败 ch=%s: %s",
                        ch_id,
                        exc,
                    )
                    chapter_md_path = None

                if chapter_md_path is not None:
                    try:
                        await asyncio.to_thread(
                            register_chapter_overview_md,
                            session_id,
                            topic,
                            ch_id,
                            ch_title,
                            chapter_md_path,
                            user_id,
                            [],
                        )
                    except Exception as exc:  # pylint: disable=broad-except
                        logger.warning(
                            "预习手册 markdown 登记失败 ch=%s: %s",
                            ch_id,
                            exc,
                        )

                chapter_md_block = {
                    "id": f"md_ch{ch_id}",
                    "type": "md",
                    "title": f"第{ch_id}章 {ch_title} — 预习手册",
                    "status": "ready",
                    "chapter_id": ch_id,
                    "data": {
                        "subtype": "chapter_content",
                        "markdown": chapter_md_content,
                        "md_path": chapter_md_rel,
                    },
                }
                upsert_canvas_block(session_id, chapter_md_block)
                if chapter_md_rel:
                    append_session_file(
                        session_id,
                        chapter_md_rel,
                        f"第{ch_id}章 {ch_title} · 预习手册",
                        "md",
                    )
                yield sse_event(
                    "workspace_update",
                    event="block_created",
                    session_id=session_id,
                    block=chapter_md_block,
                )
                logger.info("预习手册已推送: 第%d章 %s", ch_id, ch_title)

        # ── 3. 逐章串行生成 TeX/Exercises/TTS ─────────────────────
        for i, ch_info in enumerate(chapters):
            ch_id = ch_info.get("chapter_id", i + 1)
            ch_title = ch_info.get("title", f"第{ch_id}章")
            ch_base_pct = int(15 + pct_per_chapter * i)
            research_path = course.chapter_dir(ch_id) / "research.json"

            chapter_status_block = {
                "id": f"chapter_{ch_id}_status",
                "type": "chapter_status",
                "title": f"第{ch_id}章 {ch_title}",
                "status": "generating",
                "chapter_id": ch_id,
                "data": {"stage": "tex", "index": i, "total": total_ch},
            }
            upsert_canvas_block(
                session_id,
                chapter_status_block,
                stage="generating",
                workspace_patch={"current_chapter_id": ch_id},
            )
            yield sse_event(
                "chapter_start",
                index=i,
                total=total_ch,
                chapter_id=ch_id,
                title=ch_title,
                stage="tex",
            )
            yield sse_event(
                "workspace_update",
                event="block_created",
                session_id=session_id,
                block=chapter_status_block,
            )

            # ── 3a. TeX Writer ───────────────────────────────────
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
                "TeX Writer 完成: 第%d章 (PDF有效=%s)", ch_id, _pdf_is_ready(pdf_path)
            )

            # （预习手册已在 Researcher 完成后推送，此处不再重复生成）

            # ── 2b++. PDF 完成后立即推送给前端 ──────────────────────
            pdf_ready = _pdf_is_ready(pdf_path)
            pdf_rel = to_rel_path(str(pdf_path)) if pdf_ready else ""
            num_frames = count_beamer_frames(tex_path)
            pdf_block = None
            if pdf_ready:
                pdf_file = {
                    "file_id": pdf_rel,
                    "file_type": "pdf",
                    "title": f"第{ch_id}章 {ch_title}",
                }
                all_files_for_session.append(pdf_file)
                append_session_file(
                    session_id, pdf_rel, f"第{ch_id}章 {ch_title}", "pdf"
                )
                pdf_block = {
                    "id": f"pdf_ch{ch_id}",
                    "type": "pdf",
                    "title": f"第{ch_id}章 {ch_title}",
                    "status": "ready",
                    "chapter_id": ch_id,
                    "data": {
                        "url": f"/api/immersive/files/{pdf_rel}",
                        "pdf_path": pdf_rel,
                        "num_pages": num_frames,
                        "audio_enabled": enable_audio,
                        "audio_files": [],  # TTS 尚未完成，后续补充
                    },
                }
                upsert_canvas_block(session_id, pdf_block)
                yield sse_event(
                    "workspace_update",
                    event="block_created",
                    session_id=session_id,
                    block=pdf_block,
                )
                logger.info("PDF block 已推送: 第%d章 %s", ch_id, ch_title)

            # ── 2c. Exercises ────────────────────────────────────
            exercises_path = course.exercises_file(ch_id)
            ex_rel = ""
            quiz_block = None

            if enable_exercises:
                exercises_pct = int(ch_base_pct + pct_per_chapter * 0.7)
                yield sse_event(
                    "progress",
                    stage="exercises",
                    pct=exercises_pct,
                    message=f"✏️ 生成习题 ({i + 1}/{total_ch}): {ch_title}",
                )

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

                # ── 2c+. 习题完成后立即推送给前端 ────────────────────
                ex_rel = (
                    to_rel_path(str(exercises_path)) if exercises_path.exists() else ""
                )
                if exercises_path.exists() and ex_rel:
                    append_session_file(
                        session_id, ex_rel, f"第{ch_id}章 {ch_title} 习题", "md"
                    )
                    quiz_block = {
                        "id": f"quiz_ch{ch_id}_bank",
                        "type": "quiz_batch",
                        "title": f"第{ch_id}章小测",
                        "status": "ready",
                        "chapter_id": ch_id,
                        "data": {
                            "source": "exercises_md",
                            "exercises_path": ex_rel,
                            "display_limit": 3,
                            "strategy": "show_2_to_3_questions_first",
                        },
                    }
                    upsert_canvas_block(session_id, quiz_block)
                    yield sse_event(
                        "workspace_update",
                        event="block_created",
                        session_id=session_id,
                        block=quiz_block,
                    )
                    logger.info("Quiz block 已推送: 第%d章 %s", ch_id, ch_title)
            else:
                logger.info("跳过习题生成: 第%d章（用户未启用习题）", ch_id)

            # ── 2d. Speaker Notes + TTS ──────────────────────────
            tts_pct = int(ch_base_pct + pct_per_chapter * 0.85)
            speaker_notes = []
            audio_results = []

            if enable_audio and tex_path.exists() and num_frames > 0:
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
            elif not enable_audio:
                logger.info("跳过语音生成: 第%d章（用户未启用语音）", ch_id)

            # ── 收集产物，发送 chapter_done ────────────────────────
            images = []
            if images_dir.exists():
                images = [
                    f.name
                    for f in images_dir.iterdir()
                    if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                ]

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

            # 如果 TTS 生成了音频，更新已推送的 pdf_block 的 audio_files
            if audio_files_data and pdf_block:
                pdf_block["data"]["audio_files"] = audio_files_data
                upsert_canvas_block(session_id, pdf_block)
                yield sse_event(
                    "workspace_update",
                    event="block_updated",
                    session_id=session_id,
                    block=pdf_block,
                )

            ch_result = {
                "chapter_id": ch_id,
                "title": ch_title,
                "knowledge_points": ch_info.get("knowledge_points", []),
                "pdf_exists": pdf_ready,
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

            # 立刻把这一章 PDF 登记到 documents 表（即使后续章节失败也能在文档管理看到）
            try:
                await asyncio.to_thread(
                    register_single_chapter_document,
                    session_id,
                    topic,
                    ch_result,
                    [],  # 节点尚未提取，先以空列表登记，后续阶段会再补
                    user_id,
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("单章文档登记失败 ch=%s: %s", ch_id, exc)

            chapter_block_ids = [f"chapter_{ch_id}_status"]
            if pdf_block:
                chapter_block_ids.append(pdf_block["id"])
            if quiz_block:
                chapter_block_ids.append(quiz_block["id"])

            completed_chapter = {
                "chapter_id": ch_id,
                "title": ch_title,
                "status": "ready",
                "block_ids": chapter_block_ids,
                "files": [b for b in [pdf_rel, ex_rel] if b],
                "audio_enabled": enable_audio,
                "audio_files": audio_files_data,
                "speaker_notes_count": len(speaker_notes),
            }
            workspace_now = update_workspace(session_id)
            workspace_data = workspace_now.get("workspace", {}) or {}
            chapters_state = workspace_data.get("chapters", []) or []
            replaced_state = False
            for idx, item in enumerate(chapters_state):
                if item.get("chapter_id") == ch_id:
                    chapters_state[idx] = {**item, **completed_chapter}
                    replaced_state = True
                    break
            if not replaced_state:
                chapters_state.append(completed_chapter)
            generated_chapters = len(
                [c for c in chapters_state if c.get("status") == "ready"]
            )
            next_chapter_id = None
            for item in chapters_state:
                if item.get("status") in {"pending", "generating", "failed"}:
                    next_chapter_id = item.get("chapter_id")
                    break
            next_actions = [
                {"type": "start_learning", "label": "先学习已生成内容"},
            ]
            if next_chapter_id:
                next_actions.append(
                    {
                        "type": "continue_generation",
                        "label": f"继续生成第{next_chapter_id}章",
                    }
                )
            update_workspace(
                session_id,
                stage="partial_ready" if generated_chapters < total_ch else "ready",
                next_actions=next_actions,
                workspace={
                    "chapters": chapters_state,
                    "generated_chapters": generated_chapters,
                    "planned_chapters": total_ch,
                    "current_chapter_id": next_chapter_id,
                },
            )
            chapter_status_block.update(
                {
                    "status": "ready",
                    "data": {
                        **chapter_status_block.get("data", {}),
                        "stage": "ready",
                        "block_ids": chapter_block_ids,
                    },
                }
            )
            upsert_canvas_block(session_id, chapter_status_block)

            # ★ 推送 chapter_done —— 通知前端本章全部产物已就绪
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
            yield sse_event(
                "workspace_update",
                event="block_updated",
                session_id=session_id,
                block=chapter_status_block,
                next_actions=next_actions,
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

        # ── 4. 生成结束（不自动 complete，等用户确认） ──────────
        duration_minutes = max(1, int((time.time() - start_time) / 60))

        # 将每章 PDF 登记到 documents 表（文档管理页面可见）
        await asyncio.to_thread(
            register_chapter_documents,
            session_id,
            topic,
            chapter_results,
            node_ids,
            user_id,
        )

        # 更新 workspace 为 ready 状态（但不标记 session 为 completed）
        update_workspace(
            session_id,
            stage="ready",
            next_actions=[
                {"type": "start_learning", "label": "开始学习"},
                {"type": "complete_session", "label": "确认完成学习"},
            ],
            workspace={
                "generated_chapters": total_ch,
                "generation_duration_minutes": duration_minutes,
                "nodes_extracted": len(created_nodes),
            },
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
        if session_id:
            try:
                # 检查是否为"空壳"会话（一个 ready 章节都没有）
                from repositories import SessionRepository as _SR

                _repo = _SR()
                _ws = _repo._read_workspace(session_id)
                _chapters_state = (_ws.get("workspace", {}) or {}).get(
                    "chapters", []
                ) or []
                _has_any_ready = any(
                    c.get("status") == "ready" for c in _chapters_state
                )

                if not _has_any_ready:
                    # 完全没产出：清理 DB 记录 + 课程目录 + workspace 文件，避免脏数据
                    try:
                        course_slug = f"{_slugify(topic)}_{session_id}"
                        course_dir = COURSES_DIR / course_slug
                        if course_dir.exists():
                            import shutil as _shutil

                            _shutil.rmtree(course_dir, ignore_errors=True)
                        # 删 workspace 文件
                        ws_path = _repo._workspace_path(session_id)
                        if ws_path.exists():
                            ws_path.unlink()
                        msg_path = _repo._messages_path(session_id)
                        if msg_path.exists():
                            msg_path.unlink()
                        # 删 sessions 表记录
                        _repo._execute("DELETE FROM sessions WHERE id=?", (session_id,))
                        logger.info(
                            "已清理空壳沉浸式会话：%s (topic=%s)", session_id, topic
                        )
                    except Exception:  # pylint: disable=broad-except
                        logger.exception("清理空壳会话失败")
                else:
                    # 有部分章节产出：保留，标记 failed 供前端续传
                    workspace = update_workspace(
                        session_id,
                        stage="failed",
                        next_actions=[
                            {"type": "retry_generation", "label": "重试生成"},
                            {"type": "start_learning", "label": "先学习已生成内容"},
                        ],
                        workspace={"last_error": str(e)},
                    )
                    yield sse_event(
                        "workspace_update",
                        event="workspace_failed",
                        session_id=session_id,
                        workspace=workspace,
                        next_actions=workspace.get("next_actions", []),
                    )
            except Exception:  # pylint: disable=broad-except
                logger.exception("写入失败 workspace 状态失败")
        yield sse_event("error", message=str(e))


async def immersive_resume(
    session_id: str,
    user_id: str,
) -> AsyncGenerator[str, None]:
    """从中断处恢复沉浸式学习生成（断点续传）。

    读取已有 workspace 状态，找到第一个 pending/failed 章节，
    复用已有 outline 和 course_dir 继续生成。

    SSE 事件与 immersive_generate 相同。
    """
    from repositories import SessionRepository

    start_time = time.time()

    try:
        repo = SessionRepository()
        session = repo.get_by_id(session_id)
        if not session:
            yield sse_event("error", message="会话不存在")
            return
        if session.user_id != user_id:
            yield sse_event("error", message="无权操作该会话")
            return

        ws = repo._read_workspace(session_id)
        workspace_data = ws.get("workspace", {}) or {}
        topic = workspace_data.get("topic") or session.topic or "未知主题"
        enable_audio = bool(workspace_data.get("enable_audio", False))
        enable_exercises = bool(workspace_data.get("enable_exercises", True))
        chapters_state = workspace_data.get("chapters", []) or []

        if not chapters_state:
            yield sse_event("error", message="未找到大纲数据，请重新生成")
            return

        # 找到 course_dir
        from agent_core.layout import _slugify

        course_slug = f"{_slugify(topic)}_{session_id}"
        course_dir = COURSES_DIR / course_slug
        if not course_dir.exists():
            yield sse_event("error", message=f"课程目录不存在: {course_slug}")
            return

        from agent_core.layout import CourseLayout, UserDataLayout

        course = CourseLayout(course_dir=course_dir)
        outline = course.load_outline()
        if not outline or not outline.get("chapters"):
            yield sse_event("error", message="大纲文件损坏或不存在，请重新生成")
            return

        chapters = outline["chapters"]
        total_ch = len(chapters)

        # 恢复前不信旧 workspace 状态，先全量扫描磁盘产物。
        chapters_state, pending_ids, generated_chapters = _audit_resume_chapters(
            session_id,
            course,
            chapters,
            chapters_state,
            enable_audio=enable_audio,
            enable_exercises=enable_exercises,
        )
        pending_chapters = [
            (i, ch)
            for i, ch in enumerate(chapters)
            if ch.get("chapter_id", i + 1) in pending_ids
        ]
        next_chapter_id = (
            pending_chapters[0][1].get("chapter_id", pending_chapters[0][0] + 1)
            if pending_chapters
            else None
        )
        next_actions = [{"type": "start_learning", "label": "先学习已生成内容"}]
        if next_chapter_id:
            next_actions.append(
                {
                    "type": "continue_generation",
                    "label": f"继续生成第{next_chapter_id}章",
                }
            )

        update_workspace(
            session_id,
            stage="partial_ready" if pending_chapters else "ready",
            next_actions=next_actions,
            workspace={
                "chapters": chapters_state,
                "enable_audio": enable_audio,
                "enable_exercises": enable_exercises,
                "generated_chapters": generated_chapters,
                "planned_chapters": total_ch,
                "current_chapter_id": next_chapter_id,
            },
        )
        yield sse_event(
            "workspace_update",
            event="artifact_audit_done",
            session_id=session_id,
            workspace={
                "enable_audio": enable_audio,
                "generated_chapters": generated_chapters,
                "planned_chapters": total_ch,
                "pending_chapter_ids": sorted(pending_ids),
            },
            next_actions=next_actions,
        )

        if not pending_chapters:
            yield sse_event(
                "progress",
                stage="done",
                pct=100,
                message="所有章节产物校验通过，无需继续生成",
            )
            return

        yield sse_event(
            "progress",
            stage="init",
            pct=5,
            message=f"恢复生成：{topic}（已校验 {total_ch} 章，需补生成 {len(pending_chapters)} 章）",
        )

        # ── 推送已完成章节的产物到前端（避免已完成章节在前端不可见）──
        for idx_done, ch_done in enumerate(chapters):
            ch_done_id = ch_done.get("chapter_id", idx_done + 1)
            if ch_done_id in pending_ids:
                continue
            ch_done_title = ch_done.get("title", f"第{ch_done_id}章")
            artifact = _chapter_artifact_status(
                course,
                ch_done,
                idx_done,
                enable_audio=enable_audio,
                enable_exercises=enable_exercises,
            )
            # 推送预习手册
            overview_done_path = (
                course.chapter_dir(ch_done_id) / f"chapter_{ch_done_id:02d}_overview.md"
            )
            if overview_done_path.exists() and overview_done_path.stat().st_size > 50:
                md_content_done = overview_done_path.read_text(encoding="utf-8")
                md_rel_done = to_rel_path(str(overview_done_path))
                md_block_done = {
                    "id": f"md_ch{ch_done_id}",
                    "type": "md",
                    "title": f"第{ch_done_id}章 {ch_done_title} — 预习手册",
                    "status": "ready",
                    "chapter_id": ch_done_id,
                    "data": {
                        "subtype": "chapter_content",
                        "markdown": md_content_done,
                        "md_path": md_rel_done,
                    },
                }
                upsert_canvas_block(session_id, md_block_done)
                yield sse_event(
                    "workspace_update",
                    event="block_created",
                    session_id=session_id,
                    block=md_block_done,
                )
            # 推送 PDF
            pdf_done_path = course.pdf_file(ch_done_id)
            if artifact["checks"].get("pdf"):
                pdf_rel_done = to_rel_path(str(pdf_done_path))
                pdf_block_done = {
                    "id": f"pdf_ch{ch_done_id}",
                    "type": "pdf",
                    "title": f"第{ch_done_id}章 {ch_done_title}",
                    "status": "ready",
                    "chapter_id": ch_done_id,
                    "data": {
                        "url": f"/api/immersive/files/{pdf_rel_done}",
                        "pdf_path": pdf_rel_done,
                        "num_pages": artifact["num_frames"],
                        "audio_enabled": enable_audio,
                        "audio_files": artifact["audio_files"],
                    },
                }
                upsert_canvas_block(session_id, pdf_block_done)
                yield sse_event(
                    "workspace_update",
                    event="block_created",
                    session_id=session_id,
                    block=pdf_block_done,
                )
            # 推送习题
            exercises_done_path = course.exercises_file(ch_done_id)
            if artifact["checks"].get("exercises") and enable_exercises:
                ex_rel_done = to_rel_path(str(exercises_done_path))
                quiz_block_done = {
                    "id": f"quiz_ch{ch_done_id}_bank",
                    "type": "quiz_batch",
                    "title": f"第{ch_done_id}章小测",
                    "status": "ready",
                    "chapter_id": ch_done_id,
                    "data": {
                        "source": "exercises_md",
                        "exercises_path": ex_rel_done,
                        "display_limit": 3,
                        "strategy": "show_2_to_3_questions_first",
                    },
                }
                upsert_canvas_block(session_id, quiz_block_done)
                yield sse_event(
                    "workspace_update",
                    event="block_created",
                    session_id=session_id,
                    block=quiz_block_done,
                )
            # 推送章节状态
            chapter_done_block_ids = [f"chapter_{ch_done_id}_status"]
            if artifact["checks"].get("pdf"):
                chapter_done_block_ids.append(f"pdf_ch{ch_done_id}")
            if artifact["checks"].get("exercises") and enable_exercises:
                chapter_done_block_ids.append(f"quiz_ch{ch_done_id}_bank")
            done_status_block = {
                "id": f"chapter_{ch_done_id}_status",
                "type": "chapter_status",
                "title": f"第{ch_done_id}章 {ch_done_title}",
                "status": "ready",
                "chapter_id": ch_done_id,
                "data": {"stage": "ready", "block_ids": chapter_done_block_ids},
            }
            upsert_canvas_block(session_id, done_status_block)
            yield sse_event(
                "workspace_update",
                event="block_updated",
                session_id=session_id,
                block=done_status_block,
            )
        logger.info(
            "resume: 已推送 %d 个已完成章节的产物到前端",
            total_ch - len(pending_chapters),
        )

        # 重建 agents
        layout = UserDataLayout(root=DOCUMENTS_DIR, user_id=user_id)
        agents = build_sub_agents(layout, user_id=user_id)

        tts_llm = get_llm(user_id) if enable_audio else None
        chapter_results = []
        all_files_for_session = []
        pct_per_chapter = 75.0 / max(len(pending_chapters), 1)

        # ── 并行 Research（已存在则跳过）──────────────────────────
        # 筛选出需要执行 research 的章节
        chapters_needing_research = []
        chapters_with_research = []
        for orig_idx, ch_info in pending_chapters:
            ch_id = ch_info.get("chapter_id", orig_idx + 1)
            research_path = course.chapter_dir(ch_id) / "research.json"
            course.chapter_dir(ch_id).mkdir(parents=True, exist_ok=True)
            if research_path.exists() and research_path.stat().st_size > 50:
                chapters_with_research.append((orig_idx, ch_info))
                logger.info("resume: 复用已有 research.json ch=%s", ch_id)
            else:
                chapters_needing_research.append((orig_idx, ch_info))

        # 对需要 research 的章节并行执行
        if chapters_needing_research:
            yield sse_event(
                "progress",
                stage="researcher",
                pct=16,
                message=f"🔍 并行检索 {len(chapters_needing_research)} 章资料...",
            )

            research_chapters_list = [
                ch_info for _, ch_info in chapters_needing_research
            ]
            research_results = await _parallel_research_all_chapters(
                topic=topic,
                chapters=research_chapters_list,
                course=course,
                layout=layout,
                user_id=user_id,
                max_concurrency=len(research_chapters_list),
            )
            logger.info(
                "resume: 并行 research 完成，%d 章成功",
                sum(1 for r in research_results if r["success"]),
            )
        else:
            yield sse_event(
                "progress",
                stage="researcher",
                pct=20,
                message="⏭️ 所有章节资料已就绪，跳过检索",
            )

        # ── 逐章推送预习手册（Research 完成后统一推送）──────────────
        for orig_idx, ch_info in pending_chapters:
            ch_id = ch_info.get("chapter_id", orig_idx + 1)
            ch_title = ch_info.get("title", f"第{ch_id}章")
            research_path = course.chapter_dir(ch_id) / "research.json"

            # 规范化 research.raw_text
            try:
                if _normalize_research_raw_text_file(research_path):
                    logger.info("resume: 已规范化 research.raw_text ch=%s", ch_id)
            except Exception as exc:
                logger.warning(
                    "resume: 规范化 research.raw_text 失败 ch=%s: %s", ch_id, exc
                )

            # 预习手册 Markdown
            overview_path_resume = (
                course.chapter_dir(ch_id) / f"chapter_{ch_id:02d}_overview.md"
            )
            overview_exists = (
                overview_path_resume.exists()
                and overview_path_resume.stat().st_size > 50
            )
            if not overview_exists:
                chapter_md_content = _build_chapter_summary_md(
                    ch_title, ch_info, research_path
                )
                if chapter_md_content:
                    try:
                        overview_path_resume.parent.mkdir(parents=True, exist_ok=True)
                        overview_path_resume.write_text(
                            chapter_md_content, encoding="utf-8"
                        )
                    except Exception as exc:
                        logger.warning("resume: 预习手册落盘失败 ch=%s: %s", ch_id, exc)
                        chapter_md_content = ""
            else:
                chapter_md_content = overview_path_resume.read_text(encoding="utf-8")

            if chapter_md_content:
                chapter_md_rel = to_rel_path(str(overview_path_resume))
                chapter_md_block = {
                    "id": f"md_ch{ch_id}",
                    "type": "md",
                    "title": f"第{ch_id}章 {ch_title} — 预习手册",
                    "status": "ready",
                    "chapter_id": ch_id,
                    "data": {
                        "subtype": "chapter_content",
                        "markdown": chapter_md_content,
                        "md_path": chapter_md_rel,
                    },
                }
                upsert_canvas_block(session_id, chapter_md_block)
                if chapter_md_rel:
                    append_session_file(
                        session_id,
                        chapter_md_rel,
                        f"第{ch_id}章 {ch_title} · 预习手册",
                        "md",
                    )
                yield sse_event(
                    "workspace_update",
                    event="block_created",
                    session_id=session_id,
                    block=chapter_md_block,
                )
                logger.info("resume: 预习手册已推送 ch=%s", ch_id)

        # ── 逐章串行生成 TeX/Exercises/TTS ────────────────────────
        for progress_idx, (orig_idx, ch_info) in enumerate(pending_chapters):
            ch_id = ch_info.get("chapter_id", orig_idx + 1)
            ch_title = ch_info.get("title", f"第{ch_id}章")
            ch_base_pct = int(15 + pct_per_chapter * progress_idx)
            research_path = course.chapter_dir(ch_id) / "research.json"

            chapter_status_block = {
                "id": f"chapter_{ch_id}_status",
                "type": "chapter_status",
                "title": f"第{ch_id}章 {ch_title}",
                "status": "generating",
                "chapter_id": ch_id,
                "data": {"stage": "tex", "index": orig_idx, "total": total_ch},
            }
            upsert_canvas_block(
                session_id,
                chapter_status_block,
                stage="generating",
                workspace_patch={"current_chapter_id": ch_id},
            )
            yield sse_event(
                "chapter_start",
                index=orig_idx,
                total=total_ch,
                chapter_id=ch_id,
                title=ch_title,
                stage="tex",
            )
            yield sse_event(
                "workspace_update",
                event="block_created",
                session_id=session_id,
                block=chapter_status_block,
            )

            # ── TeX Writer（PDF 已存在则跳过）──
            tex_pct = int(ch_base_pct + pct_per_chapter * 0.4)
            tex_path = course.tex_file(ch_id)
            pdf_path = course.pdf_file(ch_id)
            images_dir = course.chapter_images_dir(ch_id)
            tex_done = _pdf_is_ready(pdf_path)
            if tex_done:
                yield sse_event(
                    "progress",
                    stage="tex",
                    pct=tex_pct,
                    message=f"⏭️ 已有 PDF，跳过 ({progress_idx + 1}/{len(pending_chapters)}): {ch_title}",
                )
                logger.info("resume: 复用已有 PDF ch=%s", ch_id)
            else:
                yield sse_event(
                    "progress",
                    stage="tex",
                    pct=tex_pct,
                    message=f"📄 生成 PDF ({progress_idx + 1}/{len(pending_chapters)}): {ch_title}",
                )
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

            # ── Exercises（已存在则跳过，未启用则跳过）──
            exercises_pct = int(ch_base_pct + pct_per_chapter * 0.7)
            exercises_path = course.exercises_file(ch_id)
            if enable_exercises:
                exercises_done = (
                    exercises_path.exists() and exercises_path.stat().st_size > 50
                )
                if exercises_done:
                    yield sse_event(
                        "progress",
                        stage="exercises",
                        pct=exercises_pct,
                        message=f"⏭️ 已有习题，跳过 ({progress_idx + 1}/{len(pending_chapters)}): {ch_title}",
                    )
                    logger.info("resume: 复用已有 exercises ch=%s", ch_id)
                else:
                    yield sse_event(
                        "progress",
                        stage="exercises",
                        pct=exercises_pct,
                        message=f"✏️ 生成习题 ({progress_idx + 1}/{len(pending_chapters)}): {ch_title}",
                    )
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
            else:
                logger.info("resume: 用户未启用习题生成，跳过 ch=%s", ch_id)

            # ── Speaker Notes + TTS（音频已齐则跳过）──
            from services.immersive.tts import (
                count_beamer_frames,
                generate_speaker_notes,
                run_tts_for_chapter,
            )

            num_frames = count_beamer_frames(tex_path)
            speaker_notes = []
            audio_results = []
            audio_dir = course.chapter_dir(ch_id) / "audio"
            existing_audio = (
                sorted(
                    [f.name for f in audio_dir.iterdir() if f.suffix.lower() == ".wav"]
                )
                if audio_dir.exists()
                else []
            )
            tts_done = num_frames > 0 and len(existing_audio) >= num_frames

            if not enable_audio:
                logger.info("resume: 跳过语音生成 ch=%s（用户未启用语音）", ch_id)
            elif tts_done:
                # 仅复用磁盘上已有的音频，不再重跑 TTS
                yield sse_event(
                    "progress",
                    stage="tts",
                    pct=int(ch_base_pct + pct_per_chapter * 0.85),
                    message=f"⏭️ 已有语音，跳过 ({len(existing_audio)} 段): {ch_title}",
                )
                logger.info(
                    "resume: 复用已有 TTS ch=%s (%d 段)", ch_id, len(existing_audio)
                )
                audio_results = [
                    {"filename": fn, "success": True, "duration_seconds": 0}
                    for fn in existing_audio
                ]
                # speaker_notes 若已落盘也读回来
                notes_path = course.chapter_dir(ch_id) / "speaker_notes.json"
                if notes_path.exists():
                    try:
                        speaker_notes = json.loads(
                            notes_path.read_text(encoding="utf-8")
                        )
                    except Exception:
                        speaker_notes = []
            elif tex_path.exists() and num_frames > 0:
                yield sse_event(
                    "progress",
                    stage="tts",
                    pct=int(ch_base_pct + pct_per_chapter * 0.85),
                    message=f"🔊 生成语音: {ch_title} ({num_frames}页)",
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

            # ── 收集产物 ──
            images = []
            if images_dir.exists():
                images = [
                    f.name
                    for f in images_dir.iterdir()
                    if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                ]
            pdf_ready = _pdf_is_ready(pdf_path)
            pdf_rel = to_rel_path(str(pdf_path)) if pdf_ready else ""
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
                "pdf_exists": pdf_ready,
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

            # 立刻把这一章 PDF 登记到 documents 表（即使后续章节失败也能在文档管理看到）
            try:
                await asyncio.to_thread(
                    register_single_chapter_document,
                    session_id,
                    topic,
                    ch_result,
                    [],
                    user_id,
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("单章文档登记失败 ch=%s: %s", ch_id, exc)

            # （预习手册已在 Researcher 完成后推送，此处不再重复生成）

            # 更新 canvas blocks
            ready_blocks = []
            chapter_block_ids = [f"chapter_{ch_id}_status"]
            if pdf_ready:
                pdf_file = {
                    "file_id": pdf_rel,
                    "file_type": "pdf",
                    "title": f"第{ch_id}章 {ch_title}",
                }
                all_files_for_session.append(pdf_file)
                append_session_file(
                    session_id, pdf_rel, f"第{ch_id}章 {ch_title}", "pdf"
                )
                pdf_block = {
                    "id": f"pdf_ch{ch_id}",
                    "type": "pdf",
                    "title": f"第{ch_id}章 {ch_title}",
                    "status": "ready",
                    "chapter_id": ch_id,
                    "data": {
                        "url": f"/api/immersive/files/{pdf_rel}",
                        "pdf_path": pdf_rel,
                        "num_pages": num_frames,
                        "audio_enabled": enable_audio,
                        "audio_files": audio_files_data,
                    },
                }
                upsert_canvas_block(session_id, pdf_block)
                ready_blocks.append(pdf_block)
                chapter_block_ids.append(pdf_block["id"])

            if exercises_path.exists() and ex_rel:
                append_session_file(
                    session_id, ex_rel, f"第{ch_id}章 {ch_title} 习题", "md"
                )
                quiz_block = {
                    "id": f"quiz_ch{ch_id}_bank",
                    "type": "quiz_batch",
                    "title": f"第{ch_id}章小测",
                    "status": "ready",
                    "chapter_id": ch_id,
                    "data": {
                        "source": "exercises_md",
                        "exercises_path": ex_rel,
                        "display_limit": 3,
                        "strategy": "show_2_to_3_questions_first",
                    },
                }
                upsert_canvas_block(session_id, quiz_block)
                ready_blocks.append(quiz_block)
                chapter_block_ids.append(quiz_block["id"])

            # 更新 chapters_state
            completed_chapter = {
                "chapter_id": ch_id,
                "title": ch_title,
                "status": "ready",
                "block_ids": chapter_block_ids,
                "files": [b for b in [pdf_rel, ex_rel] if b],
                "audio_enabled": enable_audio,
                "audio_files": audio_files_data,
                "speaker_notes_count": len(speaker_notes),
            }
            for idx2, item in enumerate(chapters_state):
                if item.get("chapter_id") == ch_id:
                    chapters_state[idx2] = {**item, **completed_chapter}
                    break
            else:
                chapters_state.append(completed_chapter)

            generated_chapters = len(
                [c for c in chapters_state if c.get("status") == "ready"]
            )
            next_chapter_id = None
            for item in chapters_state:
                if item.get("status") in {"pending", "generating", "failed"}:
                    next_chapter_id = item.get("chapter_id")
                    break
            next_actions = [{"type": "start_learning", "label": "先学习已生成内容"}]
            if next_chapter_id:
                next_actions.append(
                    {
                        "type": "continue_generation",
                        "label": f"继续生成第{next_chapter_id}章",
                    }
                )

            update_workspace(
                session_id,
                stage="partial_ready" if generated_chapters < total_ch else "ready",
                next_actions=next_actions,
                workspace={
                    "chapters": chapters_state,
                    "generated_chapters": generated_chapters,
                    "planned_chapters": total_ch,
                    "current_chapter_id": next_chapter_id,
                },
            )
            chapter_status_block.update(
                {
                    "status": "ready",
                    "data": {
                        **chapter_status_block.get("data", {}),
                        "stage": "ready",
                        "block_ids": chapter_block_ids,
                    },
                }
            )
            upsert_canvas_block(session_id, chapter_status_block)

            yield sse_event(
                "progress",
                stage="tex",
                pct=min(int(ch_base_pct + pct_per_chapter), 90),
                message=f"✅ 第 {ch_id} 章完成: {ch_title}",
            )
            yield sse_event(
                "chapter_done", index=orig_idx, total=total_ch, data=ch_result
            )
            yield sse_event(
                "workspace_update",
                event="block_updated",
                session_id=session_id,
                block=chapter_status_block,
                next_actions=next_actions,
            )
            for block in ready_blocks:
                yield sse_event(
                    "workspace_update",
                    event="block_created",
                    session_id=session_id,
                    block=block,
                    next_actions=next_actions,
                )

            # 归档
            try:
                from services.asset_service import (
                    archive_immersive_chapter,
                    pack_chapter_bundle,
                )

                ch_dir = course.chapter_dir(ch_id)
                await asyncio.to_thread(
                    archive_immersive_chapter, ch_dir, topic, ch_dir.name, session_id
                )
            except Exception as e:
                logger.warning("章节 %d 资产归档失败: %s", ch_id, e)
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
            except Exception as e:
                logger.warning("章节 %d 打包失败: %s", ch_id, e)

        # 知识图谱抽取（仅对新生成的章节）
        yield sse_event(
            "progress", stage="nodes", pct=92, message="🧠 正在抽取知识图谱节点..."
        )
        from services.immersive.node_extractor import extract_and_persist_nodes

        new_chapters_info = [chapters[i] for i, _ in pending_chapters]
        created_nodes = await asyncio.to_thread(
            extract_and_persist_nodes,
            session_id,
            topic,
            new_chapters_info,
            tts_llm,
            user_id,
        )
        if created_nodes:
            yield sse_event(
                "nodes_extracted",
                nodes=[{"id": n["id"], "title": n["title"]} for n in created_nodes],
                new_count=sum(1 for n in created_nodes if not n.get("existed")),
            )

        yield sse_event("progress", stage="done", pct=100, message="🎉 恢复生成完成！")
        yield sse_event(
            "done",
            topic=topic,
            session_id=session_id,
            course_dir=str(course.course_dir),
            chapters=chapter_results,
            nodes_extracted=len(created_nodes),
            duration_minutes=max(1, int((time.time() - start_time) / 60)),
        )

    except Exception as e:
        logger.exception("沉浸式学习恢复生成失败")
        yield sse_event("error", message=str(e))
