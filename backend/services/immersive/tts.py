"""TTS 与讲解稿（speaker notes）相关工具。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from agent_core.llm.base import BaseLLM
from agent_core.tool.tts_say import say_batch_synthesize

logger = logging.getLogger(__name__)


def count_beamer_frames(tex_path: Path) -> int:
    """统计 Beamer 讲义的 frame 数量。"""
    if not tex_path.exists():
        return 0
    return tex_path.read_text(encoding="utf-8").count(r"\begin{frame}")


def generate_speaker_notes(llm: BaseLLM, tex_path: Path, num_pages: int) -> List[str]:
    """根据 LaTeX 源码为每一页生成讲解旁白，返回字符串列表。"""
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


def run_tts_for_chapter(
    chapter_dir: Path, speaker_notes: List[str]
) -> List[Dict[str, Any]]:
    """对单个章节的讲解稿进行 macOS Say 批量合成。"""
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
