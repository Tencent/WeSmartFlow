#!/usr/bin/env python3
"""
macOS Say TTS 工具
==================
直接调用 macOS 系统 `say` 命令将文本合成为 WAV 音频文件，无需启动任何服务。
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseTool

logger = logging.getLogger("tts_say")


# ─── 核心工具函数 ──────────────────────────────────────────────


def _say_to_wav(
    text: str,
    output_path: str,
    voice: str = "Tingting",
    rate: int = 210,
) -> Dict[str, Any]:
    """
    使用 macOS say 命令将文本合成为 WAV 文件。

    流程：say → AIFF → afconvert → WAV (PCM 16bit, 24000Hz)
    """
    if not text.strip():
        return {
            "success": False,
            "error": "文本为空",
            "path": "",
            "duration_seconds": 0,
        }

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp_aiff:
        aiff_path = tmp_aiff.name

    try:
        t0 = time.time()

        subprocess.run(
            ["say", "-v", voice, "-r", str(rate), "-o", aiff_path, text],
            check=True,
            timeout=120,
            capture_output=True,
        )

        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@24000", aiff_path, str(out_path)],
            check=True,
            timeout=30,
            capture_output=True,
        )

        elapsed = time.time() - t0

        duration = 0.0
        try:
            with wave.open(str(out_path), "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
        except Exception:  # pylint: disable=broad-except
            pass

        return {
            "success": True,
            "path": str(out_path),
            "duration_seconds": round(duration, 2),
            "elapsed_seconds": round(elapsed, 2),
            "error": "",
        }

    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "path": "",
            "duration_seconds": 0,
            "elapsed_seconds": 0,
            "error": f"say 命令执行失败: {e}",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "path": "",
            "duration_seconds": 0,
            "elapsed_seconds": 0,
            "error": "say 命令执行超时",
        }
    except Exception as e:  # pylint: disable=broad-except
        return {
            "success": False,
            "path": "",
            "duration_seconds": 0,
            "elapsed_seconds": 0,
            "error": str(e),
        }
    finally:
        if os.path.exists(aiff_path):
            os.unlink(aiff_path)


def say_batch_synthesize(
    items: List[Dict[str, str]],
    output_dir: str,
    voice: str = "Tingting",
    rate: int = 210,
) -> Dict[str, Any]:
    """批量合成：将多条文本逐条合成为 WAV 文件。"""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    total_t0 = time.time()

    for idx, item in enumerate(items):
        text = (item.get("text") or "").strip()
        filename = (item.get("filename") or "").strip()

        if not filename:
            filename = f"frame_{idx + 1:03d}.wav"
        if not filename.endswith(".wav"):
            filename += ".wav"

        if not text:
            results.append(
                {
                    "index": idx,
                    "filename": filename,
                    "path": "",
                    "duration_seconds": 0,
                    "success": False,
                    "error": "文本为空",
                }
            )
            continue

        out_path = out_dir / filename
        result = _say_to_wav(text, str(out_path), voice=voice, rate=rate)

        logger.info(
            f"[{idx + 1}/{len(items)}] "
            f"{'✓' if result['success'] else '✗'} "
            f"{len(text)}字 -> {result.get('duration_seconds', 0):.1f}s, "
            f"耗时 {result.get('elapsed_seconds', 0):.1f}s, "
            f"文件: {filename}"
        )

        results.append(
            {
                "index": idx,
                "filename": filename,
                "path": result.get("path", ""),
                "duration_seconds": result.get("duration_seconds", 0),
                "success": result.get("success", False),
                "error": result.get("error", ""),
            }
        )

    total_elapsed = time.time() - total_t0
    success_count = sum(1 for r in results if r["success"])
    logger.info(
        f"批量合成完成: {success_count}/{len(items)} 成功, 总耗时 {total_elapsed:.1f}s"
    )

    return {
        "voice": voice,
        "rate": rate,
        "total": len(items),
        "success_count": success_count,
        "total_seconds": round(total_elapsed, 2),
        "output_dir": str(out_dir),
        "results": results,
    }


# ─── BaseTool 封装（适配 agent_core BaseTool 类属性模式）─────────


class TTSSayTool(BaseTool):
    """macOS Say 文本转语音工具，直接调用系统 say 命令，无需启动服务。"""

    name = "tts_say"
    description = (
        "使用 macOS 系统 say 命令将文本批量合成为 WAV 音频文件。"
        "速度极快，适合课件讲解音频的批量生成。"
        "直接调用系统命令，无需启动任何服务。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": (
                    '要合成的文本列表，每项为 {"text": "...", "filename": "frame_001.wav"}。'
                    "filename 可选，为空则自动生成。"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "要合成的文本"},
                        "filename": {
                            "type": "string",
                            "description": "输出文件名，可选",
                        },
                    },
                    "required": ["text"],
                },
            },
            "output_dir": {
                "type": "string",
                "description": "输出目录的绝对路径，不存在会自动创建",
            },
            "voice": {
                "type": "string",
                "description": "macOS 语音名称，默认 Tingting（中文大陆女声）",
            },
            "rate": {
                "type": "integer",
                "description": "语速（词/分钟），默认 210，范围约 80~300",
            },
        },
        "required": ["items", "output_dir"],
    }

    def run(
        self,
        items: List[Dict[str, str]],
        output_dir: str,
        voice: str = "Tingting",
        rate: int = 210,
        **_: Any,
    ) -> Dict[str, Any]:
        return say_batch_synthesize(
            items=items,
            output_dir=output_dir,
            voice=voice,
            rate=rate,
        )


tts_say_tool = TTSSayTool()

__all__ = [
    "TTSSayTool",
    "tts_say_tool",
    "say_batch_synthesize",
    "_say_to_wav",
]
