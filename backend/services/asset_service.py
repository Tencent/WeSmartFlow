"""
AssetService：产物资产分类存储服务

将所有生成的产物（PDF、图片、语音）备份到 data/assets/ 下分类存储。
目录结构：
  data/assets/
    ├── pdf/          # 所有生成的 PDF（卡片 + 沉浸式课件）
    ├── images/       # 所有生成的图片（含提示词 meta）
    ├── audio/        # 所有生成的语音文件
    └── files/        # 按章打包的学习包（PDF + 语音 + 习题）
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import DATA_DIR

logger = logging.getLogger(__name__)

# 资产根目录
ASSETS_DIR = DATA_DIR / "assets"
ASSETS_PDF_DIR = ASSETS_DIR / "pdf"
ASSETS_IMAGES_DIR = ASSETS_DIR / "images"
ASSETS_AUDIO_DIR = ASSETS_DIR / "audio"
ASSETS_FILES_DIR = ASSETS_DIR / "files"

# 确保目录存在
for _d in [
    ASSETS_DIR,
    ASSETS_PDF_DIR,
    ASSETS_IMAGES_DIR,
    ASSETS_AUDIO_DIR,
    ASSETS_FILES_DIR,
]:
    _d.mkdir(parents=True, exist_ok=True)


def _safe_copy(src: Path, dst: Path) -> bool:
    """安全复制文件，如果目标已存在则跳过。"""
    if not src.exists():
        return False
    if dst.exists():
        # 文件已存在，跳过
        return True
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        return True
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("资产备份失败 %s → %s: %s", src, dst, e)
        return False


def archive_pdf(
    src_path: Path,
    source_type: str = "card",
    title: str = "",
    session_id: str = "",
) -> Optional[Path]:
    """
    将 PDF 文件备份到 assets/pdf/ 目录。

    Args:
        src_path: 源 PDF 文件路径
        source_type: 来源类型，'card'（人机交互卡片）或 'immersive'（沉浸式课件）
        title: 文档标题
        session_id: 关联的会话 ID

    Returns:
        备份后的文件路径，失败返回 None
    """
    if not src_path.exists():
        return None

    # 使用 source_type + 原文件名 作为备份文件名，避免冲突
    dst_name = f"{source_type}_{src_path.name}"
    dst = ASSETS_PDF_DIR / dst_name

    # 同时保存元信息
    meta = {
        "source_type": source_type,
        "title": title,
        "session_id": session_id,
        "original_path": str(src_path),
        "archived_at": datetime.now().isoformat(),
    }
    meta_path = ASSETS_PDF_DIR / f"{dst_name}.meta.json"

    if _safe_copy(src_path, dst):
        try:
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:  # pylint: disable=broad-except
            pass
        return dst
    return None


def archive_image(
    src_path: Path,
    prompt: str = "",
    source_type: str = "immersive",
    chapter: str = "",
) -> Optional[Path]:
    """
    将图片文件备份到 assets/images/ 目录，同时保存提示词信息。

    Args:
        src_path: 源图片文件路径
        prompt: 生成图片的提示词
        source_type: 来源类型
        chapter: 所属章节

    Returns:
        备份后的文件路径，失败返回 None
    """
    if not src_path.exists():
        return None

    dst_name = f"{source_type}_{src_path.name}"
    dst = ASSETS_IMAGES_DIR / dst_name

    # 保存图片元信息（含提示词）
    meta = {
        "source_type": source_type,
        "prompt": prompt,
        "chapter": chapter,
        "original_path": str(src_path),
        "archived_at": datetime.now().isoformat(),
    }
    meta_path = ASSETS_IMAGES_DIR / f"{dst_name}.meta.json"

    if _safe_copy(src_path, dst):
        try:
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:  # pylint: disable=broad-except
            pass
        return dst
    return None


def archive_audio(
    src_path: Path,
    text: str = "",
    source_type: str = "immersive",
    chapter: str = "",
    frame_index: int = 0,
) -> Optional[Path]:
    """
    将语音文件备份到 assets/audio/ 目录。

    Args:
        src_path: 源音频文件路径
        text: 对应的讲解文本
        source_type: 来源类型
        chapter: 所属章节
        frame_index: 帧序号

    Returns:
        备份后的文件路径，失败返回 None
    """
    if not src_path.exists():
        return None

    dst_name = f"{source_type}_{src_path.name}"
    if chapter:
        dst_name = f"{source_type}_{chapter}_{src_path.name}"
    dst = ASSETS_AUDIO_DIR / dst_name

    meta = {
        "source_type": source_type,
        "text": text,
        "chapter": chapter,
        "frame_index": frame_index,
        "original_path": str(src_path),
        "archived_at": datetime.now().isoformat(),
    }
    meta_path = ASSETS_AUDIO_DIR / f"{dst_name}.meta.json"

    if _safe_copy(src_path, dst):
        try:
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:  # pylint: disable=broad-except
            pass
        return dst
    return None


def archive_immersive_chapter(
    chapter_dir: Path, topic: str, chapter_id: str, session_id: str = ""
) -> dict:
    """
    归档沉浸式课件某一章的所有产物。

    Args:
        chapter_dir: 章节目录路径
        topic: 课程主题
        chapter_id: 章节 ID（如 chapter_01）
        session_id: 会话 ID

    Returns:
        归档统计 {"pdf": int, "images": int, "audio": int}
    """
    stats = {"pdf": 0, "images": 0, "audio": 0}

    # 归档 PDF
    for pdf in chapter_dir.glob("*.pdf"):
        if archive_pdf(
            pdf,
            source_type="immersive",
            title=f"{topic} - {chapter_id}",
            session_id=session_id,
        ):
            stats["pdf"] += 1

    # 归档图片（含 meta.json 中的提示词）
    images_dir = chapter_dir / "images"
    if images_dir.exists():
        for img in images_dir.glob("*.png"):
            prompt = ""
            meta_file = images_dir / f"{img.stem}.meta.json"
            if meta_file.exists():
                try:
                    meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
                    prompt = meta_data.get("prompt", "")
                except Exception:  # pylint: disable=broad-except
                    pass
            if archive_image(
                img, prompt=prompt, source_type="immersive", chapter=chapter_id
            ):
                stats["images"] += 1
        # 也备份原始 meta.json
        for meta in images_dir.glob("*.meta.json"):
            _safe_copy(meta, ASSETS_IMAGES_DIR / f"immersive_{meta.name}")

    # 归档语音
    audio_dir = chapter_dir / "audio"
    if audio_dir.exists():
        for wav in sorted(audio_dir.glob("*.wav")):
            idx = 0
            try:
                idx = int(wav.stem.split("_")[-1])
            except (ValueError, IndexError):
                pass
            if archive_audio(
                wav, source_type="immersive", chapter=chapter_id, frame_index=idx
            ):
                stats["audio"] += 1

    return stats


def _sanitize_filename(name: str) -> str:
    """将字符串转为安全的文件名（去除非法字符、压缩空白）。"""
    if not name:
        return "untitled"
    # 把 Windows/Unix 不允许的字符及空白替换为下划线
    cleaned = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", name).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    # 限制长度，避免路径过长
    if len(cleaned) > 80:
        cleaned = cleaned[:80]
    return cleaned or "untitled"


def pack_chapter_bundle(
    chapter_dir: Path,
    topic: str,
    chapter_title: str,
    chapter_id: str = "",
    session_id: str = "",
) -> Optional[Path]:
    """
    将沉浸式学习某一章的 PDF + 语音 + 习题（含答案）打包为 zip，
    保存到 data/assets/files/ 目录。

    打包文件名格式：{topic}_{chapter_title}_{YYYYMMDD_HHMMSS}.zip

    Args:
        chapter_dir: 章节目录路径，例如 <course_dir>/chapter_01/
        topic: 课程主题
        chapter_title: 章节标题（用于文件名）
        chapter_id: 章节 ID（如 "1" 或 "chapter_01"），写入 manifest
        session_id: 会话 ID，写入 manifest

    Returns:
        打包文件路径；失败返回 None
    """
    if not chapter_dir.exists() or not chapter_dir.is_dir():
        logger.warning("pack_chapter_bundle: 章节目录不存在 %s", chapter_dir)
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = _sanitize_filename(topic)
    safe_chapter = _sanitize_filename(chapter_title)
    bundle_name = f"{safe_topic}_{safe_chapter}_{timestamp}.zip"
    bundle_path = ASSETS_FILES_DIR / bundle_name

    # 收集文件：PDF、语音（整个 audio 目录）、习题 md
    pdf_files = sorted(chapter_dir.glob("*.pdf"))
    audio_dir = chapter_dir / "audio"
    audio_files = sorted(audio_dir.glob("*.wav")) if audio_dir.exists() else []
    exercises_files = sorted(chapter_dir.glob("*_exercises.md"))
    # 也把 speaker_notes 一并放入，便于回看讲解稿
    notes_files = sorted(chapter_dir.glob("speaker_notes.json"))

    if not pdf_files and not audio_files and not exercises_files:
        logger.warning(
            "pack_chapter_bundle: 章节 %s 没有可打包的产物，跳过", chapter_dir
        )
        return None

    manifest = {
        "topic": topic,
        "chapter_title": chapter_title,
        "chapter_id": chapter_id,
        "session_id": session_id,
        "packed_at": datetime.now().isoformat(),
        "contents": {
            "pdf": [p.name for p in pdf_files],
            "audio": [p.name for p in audio_files],
            "exercises": [p.name for p in exercises_files],
            "speaker_notes": [p.name for p in notes_files],
        },
    }

    try:
        with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1) PDF 放在 zip 根目录
            for pdf in pdf_files:
                zf.write(pdf, arcname=f"pdf/{pdf.name}")
            # 2) 语音文件整体放入 audio/ 子目录
            for wav in audio_files:
                zf.write(wav, arcname=f"audio/{wav.name}")
            # 3) 习题（md 含答案）放入 exercises/
            for md in exercises_files:
                zf.write(md, arcname=f"exercises/{md.name}")
            # 4) 讲解稿
            for nf in notes_files:
                zf.write(nf, arcname=f"notes/{nf.name}")
            # 5) 写入 manifest.json
            zf.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
        logger.info(
            "章节打包完成 → %s (pdf=%d, audio=%d, exercises=%d)",
            bundle_path.name,
            len(pdf_files),
            len(audio_files),
            len(exercises_files),
        )
        return bundle_path
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("章节打包失败 %s: %s", chapter_dir, e)
        # 删掉半成品 zip
        try:
            if bundle_path.exists():
                bundle_path.unlink()
        except Exception:  # pylint: disable=broad-except
            pass
        return None


def archive_card(card_pdf_path: Path, title: str = "", session_id: str = "") -> dict:
    """
    归档人机交互卡片的产物。

    Args:
        card_pdf_path: 卡片 PDF 路径
        title: 卡片标题
        session_id: 会话 ID

    Returns:
        归档统计 {"pdf": int}
    """
    stats = {"pdf": 0}
    if archive_pdf(
        card_pdf_path, source_type="card", title=title, session_id=session_id
    ):
        stats["pdf"] += 1

    # 如果有对应的 tex 文件也备份
    tex_path = card_pdf_path.with_suffix(".tex")
    if tex_path.exists():
        _safe_copy(tex_path, ASSETS_PDF_DIR / f"card_{tex_path.name}")

    return stats


def archive_existing_assets() -> dict:
    """
    扫描现有的所有产物并归档到 assets 目录。
    用于首次运行时将已有产物全部备份。

    Returns:
        归档统计
    """
    from config import CARDS_DIR

    total_stats = {"pdf": 0, "images": 0, "audio": 0}

    # 1. 归档已有的卡片 PDF
    if CARDS_DIR.exists():
        for pdf in CARDS_DIR.glob("*.pdf"):
            if archive_pdf(pdf, source_type="card"):
                total_stats["pdf"] += 1

    # 2. 归档沉浸式课件
    immersive_courses = DATA_DIR / "immersive" / "courses"
    if immersive_courses.exists():
        for topic_dir in immersive_courses.iterdir():
            if not topic_dir.is_dir():
                continue
            topic = topic_dir.name
            for chapter_dir in sorted(topic_dir.iterdir()):
                if not chapter_dir.is_dir() or not chapter_dir.name.startswith(
                    "chapter_"
                ):
                    continue
                stats = archive_immersive_chapter(chapter_dir, topic, chapter_dir.name)
                for k in total_stats:
                    total_stats[k] += stats.get(k, 0)

    logger.info("现有资产归档完成: %s", total_stats)
    return total_stats
