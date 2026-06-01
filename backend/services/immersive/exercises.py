"""沉浸式学习 - 习题获取服务。

提供结构化的习题数据（已解析的 Markdown → JSON），
前端无需再手动拼路径、fetch raw Markdown 再自行解析。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import COURSES_DIR
from repositories import SessionRepository

logger = logging.getLogger(__name__)


def _parse_exercises_md(md_text: str) -> List[Dict[str, Any]]:
    """将 exercises.md 解析为结构化习题列表。

    兼容多种历史/当前格式：
      A. 新格式（推荐，由当前 agent 输出）：
         ### 第1题 [简单]
         **题干：** 题目内容
         A. xxx
         B. xxx
         **答案：** A
         **解析：** xxxx
      B. 旧格式（### N. 选择题 + 答案：x）
      C. <details><summary>答案与解析</summary>...</details> 历史格式

    输出每项除常规字段外还包含 difficulty: 'easy' | 'medium' | 'hard'。
    顺序兜底：按 difficulty 分组排序（简单→中等→困难），同组内按原始顺序。
    """
    questions: List[Dict[str, Any]] = []

    # 用 ### 开头的行做切分（覆盖 ## 与 ### 两种）
    blocks = re.split(r"\n(?=#{2,3}\s)", md_text.strip())

    # 难度关键词映射
    diff_map = [
        ("easy", ["简单", "easy", "基础", "入门"]),
        ("medium", ["中等", "中级", "medium", "普通"]),
        ("hard", ["困难", "难", "hard", "进阶", "挑战"]),
    ]

    def _detect_difficulty(text: str) -> str:
        low = text.lower()
        for key, words in diff_map:
            for w in words:
                if w in text or w.lower() in low:
                    return key
        return ""

    auto_num = 0
    for block in blocks:
        block = block.strip()
        if not block.startswith("#"):
            continue

        # 取首行作为标题
        first_nl = block.find("\n")
        head_line = block if first_nl == -1 else block[:first_nl]
        body = "" if first_nl == -1 else block[first_nl + 1 :]

        # 跳过明显的章节大标题（不含"题"且不含数字编号的）
        head_clean = re.sub(r"^#{2,3}\s*", "", head_line).strip()

        # 提取题号：优先识别 "第N题"，其次 "习题N"，再退化到开头数字
        num_match = re.search(r"第\s*(\d+)\s*题", head_clean)
        if not num_match:
            num_match = re.search(r"习题\s*[（(]?\s*(\d+)", head_clean)
        if not num_match:
            num_match = re.match(r"(\d+)[\.\s、]", head_clean)
        if num_match:
            q_num = int(num_match.group(1))
        else:
            # 没有数字编号，但若不像题目（不含"题"/选项/答案），跳过
            if "题" not in head_clean and "答案" not in body and "A." not in body:
                continue
            auto_num += 1
            q_num = auto_num

        # 难度：先从标题找，再从整块找
        difficulty = _detect_difficulty(head_clean) or _detect_difficulty(body)

        # 处理历史 <details> 块
        details_match = re.search(
            r"<details[^>]*>.*?<summary[^>]*>.*?</summary>(.*?)</details>",
            body,
            re.DOTALL | re.IGNORECASE,
        )
        explanation = ""
        answer_text = ""
        if details_match:
            detail_content = details_match.group(1).strip()
            ans_m = re.search(
                r"(?:答案|正确答案)[：:\s]*\*{0,2}\s*([A-Da-d])", detail_content
            )
            if ans_m:
                answer_text = ans_m.group(1).upper()
            expl_m = re.search(r"(?:解析|解释)[：:]\s*(.+)", detail_content, re.DOTALL)
            if expl_m:
                explanation = expl_m.group(1).strip()
            elif not ans_m:
                explanation = detail_content
            body = body[: details_match.start()] + body[details_match.end() :]

        # 提取"答案：X"行（兼容 **答案：** A 格式）
        if not answer_text:
            ans_m = re.search(
                r"\*{0,2}\s*(?:答案|正确答案)\s*\*{0,2}\s*[：:]\s*\*{0,2}\s*([A-Da-d])",
                body,
            )
            if ans_m:
                answer_text = ans_m.group(1).upper()

        # 提取"解析：xxx"段（兼容 **解析：** 与多行）
        if not explanation:
            expl_m = re.search(
                r"\*{0,2}\s*(?:解析|解释|分析)\s*\*{0,2}\s*[：:]\s*([\s\S]+?)(?=\n\s*(?:#{2,3}\s|$))",
                body,
            )
            if expl_m:
                explanation = expl_m.group(1).strip()

        # 提取选项：必须以 A. / B. / C. / D. 开头（也兼容 - A. / * A. / A、 / A）
        option_labels: List[str] = []
        options: List[str] = []
        for line in body.split("\n"):
            s = line.strip()
            # 跳过答案/解析/题干行
            if not s:
                continue
            if re.match(
                r"\*{0,2}\s*(?:答案|正确答案|解析|解释|分析|题干|题目)\s*\*{0,2}\s*[：:]",
                s,
            ):
                continue
            opt_m = re.match(r"^[-*]?\s*([A-D])[.、）)]\s*(.+)", s)
            if opt_m:
                lab = opt_m.group(1)
                if lab not in option_labels:  # 防重复
                    option_labels.append(lab)
                    options.append(opt_m.group(2).strip())

        # 提取题干：去掉所有已被识别为答案/解析/选项/标签的行
        stem_lines: List[str] = []
        for line in body.split("\n"):
            s = line.strip()
            if not s:
                continue
            if re.match(r"^[-*]?\s*[A-D][.、）)]", s):
                continue
            if re.match(
                r"\*{0,2}\s*(?:答案|正确答案|解析|解释|分析)\s*\*{0,2}\s*[：:]", s
            ):
                continue
            # 去掉 "**题干：**" 前缀
            s = re.sub(r"^\*{0,2}\s*(?:题干|题目)\s*\*{0,2}\s*[：:]\s*", "", s)
            if s:
                stem_lines.append(s)
        stem = "\n".join(stem_lines).strip()

        # 必须是合法选择题：≥2 个选项 + 题干非空 + 有答案
        if len(options) < 2 or not stem:
            continue

        # 正确选项 index
        correct_index = -1
        if answer_text:
            ans_letter = re.match(r"([A-D])", answer_text.upper())
            if ans_letter and ans_letter.group(1) in option_labels:
                correct_index = option_labels.index(ans_letter.group(1))

        questions.append(
            {
                "id": f"q_{q_num}",
                "num": q_num,
                "type": "choice",
                "question": stem,
                "options": options,
                "optionLabels": option_labels,
                "answer": answer_text,
                "explanation": explanation,
                "correctIndex": correct_index,
                "difficulty": difficulty or "medium",
            }
        )

    # 按难度分组排序：easy → medium → hard，组内保持原顺序
    diff_order = {"easy": 0, "medium": 1, "hard": 2}
    questions.sort(key=lambda q: (diff_order.get(q.get("difficulty", "medium"), 1),))

    # 重新编号，避免编号空洞
    for i, q in enumerate(questions, start=1):
        q["num"] = i
        q["id"] = f"q_{i}"

    return questions


def _find_exercises_path(session_id: str, chapter_id: int) -> Optional[Path]:
    """通过 workspace 信息定位习题文件路径。"""
    repo = SessionRepository()
    ws = repo._read_workspace(session_id)
    workspace = ws.get("workspace", {}) or {}
    chapters = workspace.get("chapters", []) or []

    # 优先从 canvas_blocks 中查找
    blocks = ws.get("canvas_blocks", []) or []
    for block in blocks:
        if block.get("type") == "quiz_batch" and block.get("chapter_id") == chapter_id:
            ex_path = block.get("data", {}).get("exercises_path")
            if ex_path:
                abs_path = COURSES_DIR / ex_path
                if abs_path.exists():
                    return abs_path

    # fallback: 从 chapters 状态查找
    for ch in chapters:
        if ch.get("chapter_id") == chapter_id:
            files = ch.get("files", [])
            for f in files:
                if isinstance(f, str) and "exercises" in f.lower():
                    abs_path = COURSES_DIR / f
                    if abs_path.exists():
                        return abs_path

    # 最后 fallback: 按照 session_id 遍历 COURSES_DIR
    for d in COURSES_DIR.iterdir():
        if not d.is_dir():
            continue
        if session_id in d.name:
            ch_dir = d / f"chapter_{chapter_id:02d}"
            if not ch_dir.exists():
                ch_dir = d / f"chapter_{chapter_id}"
            if ch_dir.exists():
                for f in ch_dir.iterdir():
                    if f.name.endswith("exercises.md"):
                        return f
            break

    return None


def get_exercises_for_chapter(
    session_id: str,
    chapter_id: int,
    user_id: str,
    *,
    limit: int = 0,
) -> Dict[str, Any]:
    """获取指定章节的结构化习题数据。

    Args:
        session_id: 会话 ID
        chapter_id: 章节编号
        user_id: 用户 ID（权属校验）
        limit: 返回题目数上限，0 表示全部

    Returns:
        {
            "chapter_id": int,
            "total": int,
            "questions": [...],
            "exercises_path": str,
        }

    Raises:
        ValueError: session 不属于该用户或文件不存在
    """
    # 权属校验
    repo = SessionRepository()
    session = repo.get_by_id(session_id)
    if not session or session.user_id != user_id:
        raise ValueError("会话不存在或无权访问")

    path = _find_exercises_path(session_id, chapter_id)
    if not path or not path.exists():
        return {
            "chapter_id": chapter_id,
            "total": 0,
            "questions": [],
            "exercises_path": "",
        }

    md_text = path.read_text(encoding="utf-8")
    questions = _parse_exercises_md(md_text)

    if limit > 0:
        questions = questions[:limit]

    rel_path = str(path.relative_to(COURSES_DIR)) if path else ""

    return {
        "chapter_id": chapter_id,
        "total": len(questions),
        "questions": questions,
        "exercises_path": rel_path,
    }
