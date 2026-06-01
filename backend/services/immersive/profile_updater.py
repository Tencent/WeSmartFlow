"""
沉浸式学习画像更新器

负责将习题作答结果、课程完成等事件转化为用户画像更新。
包含：
- 答题结果 → 知识点掌握度更新
- mastery.json 结构化数据维护
- profile.md 增量更新（知识点掌握部分）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from config import DOCUMENTS_DIR

logger = logging.getLogger(__name__)


def _get_mastery_file(user_id: str = "") -> Path:
    """获取指定用户的 mastery 文件路径（按 user_id 隔离）。"""
    from agent_core.layout import UserDataLayout

    layout = UserDataLayout(root=DOCUMENTS_DIR, user_id=user_id)
    return layout.mastery_file


def _load_mastery(user_id: str = "") -> Dict[str, Any]:
    """加载指定用户的 mastery.json，不存在时尝试 fallback 到旧的全局文件。"""
    mastery_file = _get_mastery_file(user_id)
    if mastery_file.exists():
        try:
            return json.loads(mastery_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("mastery.json 解析失败，将重建")
    # fallback: 尝试读取旧的全局文件（迁移兼容）
    if user_id:
        legacy_file = Path(DOCUMENTS_DIR) / "profile" / "mastery.json"
        if legacy_file.exists():
            try:
                return json.loads(legacy_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    return {"topics": {}, "last_updated": ""}


def _save_mastery(data: Dict[str, Any], user_id: str = "") -> None:
    """保存指定用户的 mastery.json。"""
    mastery_file = _get_mastery_file(user_id)
    mastery_file.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now().isoformat()
    mastery_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _accuracy_to_level(accuracy: float) -> str:
    """将正确率映射为掌握等级描述。"""
    if accuracy >= 0.9:
        return "⭐⭐⭐⭐ 熟练"
    elif accuracy >= 0.7:
        return "⭐⭐⭐ 基本掌握"
    elif accuracy >= 0.4:
        return "⭐⭐ 初步了解"
    else:
        return "⭐ 需要加强"


async def update_profile_from_quiz(
    user_id: str,
    session_id: str,
    chapter_id: int,
    chapter_title: str,
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    # 注意：下方调用 _load_mastery/_save_mastery 时传入 user_id 实现隔离
    """根据习题作答结果更新用户画像。

    Args:
        user_id: 用户 ID
        session_id: 会话 ID
        chapter_id: 章节 ID
        chapter_title: 章节标题
        results: 答题结果列表

    Returns:
        更新结果摘要
    """
    if not results:
        return {"status": "ok", "message": "无答题数据"}

    # 计算各难度正确率
    stats = {
        "简单": {"total": 0, "correct": 0},
        "中等": {"total": 0, "correct": 0},
        "困难": {"total": 0, "correct": 0},
    }

    for r in results:
        diff = r.get("difficulty", "中等")
        if diff not in stats:
            diff = "中等"
        stats[diff]["total"] += 1
        if r.get("correct"):
            stats[diff]["correct"] += 1

    total = sum(s["total"] for s in stats.values())
    correct = sum(s["correct"] for s in stats.values())
    overall_accuracy = correct / total if total > 0 else 0
    mastery_level = _accuracy_to_level(overall_accuracy)

    # 获取课程 topic（从 session 中获取）
    topic = ""
    try:
        from repositories import SessionRepository

        session = SessionRepository().get_by_id(session_id)
        if session:
            topic = (
                (session.topic or session.title or "").replace("[AI课程]", "").strip()
            )
    except Exception:
        pass

    # ── 1. 更新 mastery.json ───────────────────────────
    mastery = _load_mastery(user_id)
    topic_key = topic or f"session_{session_id}"
    if topic_key not in mastery["topics"]:
        mastery["topics"][topic_key] = {
            "first_study": datetime.now().isoformat(),
            "chapters": {},
        }

    chapter_key = f"ch{chapter_id}_{chapter_title}"
    mastery["topics"][topic_key]["chapters"][chapter_key] = {
        "accuracy": round(overall_accuracy, 2),
        "mastery_level": mastery_level,
        "total_questions": total,
        "correct_count": correct,
        "by_difficulty": {
            k: {"total": v["total"], "correct": v["correct"]}
            for k, v in stats.items()
            if v["total"] > 0
        },
        "last_attempt": datetime.now().isoformat(),
    }

    _save_mastery(mastery, user_id)

    # ── 2. 增量更新 profile.md 中的知识点掌握部分 ─────────────
    _update_profile_mastery_section(mastery, user_id)

    logger.info(
        "习题画像更新完成: topic=%s, chapter=%s, accuracy=%.0f%%",
        topic_key,
        chapter_title,
        overall_accuracy * 100,
    )

    return {
        "status": "ok",
        "accuracy": round(overall_accuracy, 2),
        "mastery_level": mastery_level,
        "details": {
            k: {"accuracy": v["correct"] / v["total"] if v["total"] > 0 else 0}
            for k, v in stats.items()
            if v["total"] > 0
        },
    }


def _update_profile_mastery_section(mastery: Dict[str, Any], user_id: str = "") -> None:
    """更新 profile.md 中的「学习过的主题」和「知识点掌握详情」段落。"""
    import re
    from agent_core.layout import UserDataLayout

    layout = UserDataLayout(root=DOCUMENTS_DIR, user_id=user_id)
    layout.ensure_dirs()
    profile_file = layout.profile_file

    # 构建掌握度段落
    topics_data = mastery.get("topics", {})
    if not topics_data:
        return

    # 构建「学习过的主题」表格
    table_lines = [
        "## 学习过的主题\n",
        "| 主题 | 章节数 | 平均掌握度 | 最近学习 |",
        "|------|--------|-----------|---------|",
    ]
    for topic_name, topic_info in topics_data.items():
        chapters = topic_info.get("chapters", {})
        if not chapters:
            continue
        accuracies = [ch.get("accuracy", 0) for ch in chapters.values()]
        avg_acc = sum(accuracies) / len(accuracies) if accuracies else 0
        avg_level = _accuracy_to_level(avg_acc)
        last_times = [ch.get("last_attempt", "") for ch in chapters.values()]
        last_time = max(last_times) if last_times else ""
        last_date = last_time[:10] if last_time else "未知"
        table_lines.append(
            f"| {topic_name} | {len(chapters)} | {avg_level} | {last_date} |"
        )

    # 构建「知识点掌握详情」
    detail_lines = ["\n## 知识点掌握详情\n"]
    for topic_name, topic_info in topics_data.items():
        chapters = topic_info.get("chapters", {})
        if not chapters:
            continue
        chapter_descs = []
        for ch_name, ch_info in chapters.items():
            level = ch_info.get("mastery_level", "待评价")
            # 去掉 ch_name 中的 "chN_" 前缀
            display_name = ch_name.split("_", 1)[-1] if "_" in ch_name else ch_name
            chapter_descs.append(f"{display_name}（{level}）")
        detail_lines.append(f"- **{topic_name}**：{'、'.join(chapter_descs)}")

    new_section = "\n".join(table_lines) + "\n" + "\n".join(detail_lines)

    # 读取现有 profile.md
    existing = ""
    if profile_file.exists():
        existing = profile_file.read_text(encoding="utf-8")

    if existing:
        # 替换已有的「学习过的主题」段落（从 ## 学习过的主题 到下一个 ## 或文件末尾）
        # 同时替换「知识点掌握详情」段落
        pattern_topics = r"## 学习过的主题\n[\s\S]*?(?=\n## (?!知识点掌握详情)|\Z)"
        pattern_detail = r"## 知识点掌握详情\n[\s\S]*?(?=\n## |\Z)"

        # 先移除旧的两个段落
        updated = re.sub(pattern_detail, "", existing)
        updated = re.sub(pattern_topics, "", updated)
        # 追加新段落
        updated = updated.rstrip() + "\n\n" + new_section + "\n"
    else:
        updated = "# 用户画像\n\n" + new_section + "\n"

    profile_file.write_text(updated, encoding="utf-8")

    # 检查是否需要压缩（防爆机制）
    _check_and_compress_profile(profile_file)


# ── Profile 压缩防爆机制 ──────────────────────────────────────────

MAX_PROFILE_CHARS = 2000  # profile.md 最大字符数


def _check_and_compress_profile(profile_file: Path) -> None:
    """检查 profile.md 是否超过阈值，超过时进行压缩。

    压缩策略（不依赖 LLM，纯规则压缩，避免额外 API 调用）：
    1. 保留「自我描述」段落完整
    2. 「学习过的主题」表格只保留最近 5 个主题
    3. 「知识点掌握详情」只保留最近 5 个主题的详情
    4. 「学习特征」段落保留最后 5 条
    """
    if not profile_file.exists():
        return

    content = profile_file.read_text(encoding="utf-8")
    if len(content) <= MAX_PROFILE_CHARS:
        return

    logger.info(
        "profile.md 超过 %d 字符（当前 %d），执行压缩",
        MAX_PROFILE_CHARS,
        len(content),
    )

    # 分段提取
    sections = {}
    current_section = "_header"
    sections[current_section] = []

    for line in content.split("\n"):
        if line.startswith("## "):
            current_section = line.strip()
            sections[current_section] = []
        else:
            sections.setdefault(current_section, []).append(line)

    # 重建压缩后的内容
    compressed_parts = []

    # 保留 header（# 用户画像）
    header = "\n".join(sections.get("_header", [])).strip()
    if header:
        compressed_parts.append(header)

    # 保留「自我描述」完整
    self_desc_key = "## 自我描述"
    if self_desc_key in sections:
        compressed_parts.append(
            self_desc_key + "\n" + "\n".join(sections[self_desc_key])
        )

    # 「学习过的主题」只保留最近 5 行数据
    topics_key = "## 学习过的主题"
    if topics_key in sections:
        lines = sections[topics_key]
        # 找到表格数据行（跳过表头和分隔线）
        header_lines = []
        data_lines = []
        for line in lines:
            if line.startswith("|---") or line.startswith("| 主题"):
                header_lines.append(line)
            elif line.startswith("|"):
                data_lines.append(line)
            else:
                header_lines.append(line)
        # 只保留最后 5 行数据
        kept_data = data_lines[-5:] if len(data_lines) > 5 else data_lines
        compressed_parts.append(topics_key + "\n" + "\n".join(header_lines + kept_data))

    # 「知识点掌握详情」只保留最近 5 个主题
    detail_key = "## 知识点掌握详情"
    if detail_key in sections:
        lines = sections[detail_key]
        # 每个主题以 "- **" 开头
        topic_lines = [line for line in lines if line.startswith("- **")]
        other_lines = [line for line in lines if not line.startswith("- **")]
        kept_topics = topic_lines[-5:] if len(topic_lines) > 5 else topic_lines
        compressed_parts.append(
            detail_key + "\n" + "\n".join(other_lines + kept_topics)
        )

    # 「学习特征」保留最后 5 条
    traits_key = "## 学习特征（AI 观察）"
    if traits_key in sections:
        lines = sections[traits_key]
        trait_lines = [line for line in lines if line.startswith("- ")]
        other_lines = [line for line in lines if not line.startswith("- ")]
        kept_traits = trait_lines[-5:] if len(trait_lines) > 5 else trait_lines
        compressed_parts.append(
            traits_key + "\n" + "\n".join(other_lines + kept_traits)
        )

    # 其他未识别的段落保留
    known_keys = {"_header", self_desc_key, topics_key, detail_key, traits_key}
    for key, lines in sections.items():
        if key not in known_keys:
            compressed_parts.append(key + "\n" + "\n".join(lines))

    compressed = "\n\n".join(compressed_parts).strip() + "\n"
    profile_file.write_text(compressed, encoding="utf-8")
    logger.info("profile.md 压缩完成：%d → %d 字符", len(content), len(compressed))
