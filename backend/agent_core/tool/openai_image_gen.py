#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAI 兼容图像生成工具。

调用兼容 OpenAI Images API 的图像生成服务（如 http://localhost:8080），
将生成的图片落盘到指定目录，文件名由内容 SHA256 前 16 位决定（幂等、防重复）。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import requests
except ImportError:
    requests = None

from .base import BaseTool


class OpenAIImageGenTool(BaseTool):
    """调用兼容 OpenAI Images API 的图像生成服务生成图片，并落盘到指定目录。"""

    name = "openai_image_generate"
    description = (
        "调用兼容 OpenAI Images API 的图像生成服务，根据文本提示词生成图片并保存到指定目录。"
        "支持指定图像尺寸（size）和负向提示词（negative_prompt）。"
        "调用成功后返回图片的本地绝对路径。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "图像描述提示词，建议使用英文，1~4000 字符。",
            },
            "output_dir": {
                "type": "string",
                "description": "图片输出目录路径，图片将保存到该目录下。",
            },
            "size": {
                "type": "string",
                "description": (
                    "图像尺寸，格式 WxH。推荐值：\n"
                    "  • 1920x1080（16:9，横图，Beamer 幻灯片首选）\n"
                    "  • 1280x960（4:3，横图，传统幻灯片）\n"
                    "  • 1024x1024（1:1，方图，通用插图）\n"
                    "  • 768x1024（3:4，竖图，人物/海报）\n"
                    "  • 1024x768（4:3，横图，场景/风景）\n"
                    "教学讲义推荐使用 1920x1080。"
                ),
            },
            "negative_prompt": {
                "type": "string",
                "description": "负向提示词，描述不希望出现的内容，如 blurry, low quality。",
            },
            "timeout": {
                "type": "integer",
                "description": "请求超时时间（秒），默认 300。",
            },
        },
        "required": ["prompt", "output_dir"],
    }

    def __init__(
        self,
        api_key: str = "any",
        base_url: str = "http://localhost:8080/v1",
        model: Optional[str] = None,
        steps: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        before_call_hook=None,
    ):
        """
        Args:
            api_key:        API Key，服务不校验时传任意字符串即可。
            base_url:       服务根地址，默认 http://localhost:8080/v1。
            model:          模型名称，为 None 时由服务端决定。
            steps:          推理步数（1~150），为 None 时由服务端决定。
            guidance_scale: CFG 引导系数（1.0~20.0），为 None 时由服务端决定。
            before_call_hook: 执行前回调（如额度检查）。
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.steps = steps
        self.guidance_scale = guidance_scale
        super().__init__(before_call_hook=before_call_hook)

    # ── 内部工具方法 ──

    @staticmethod
    def _content_hash(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()[:16]

    @staticmethod
    def _write_meta(image_path: Path, meta: Dict[str, Any]) -> None:
        meta_path = image_path.with_suffix(".meta.json")
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _build_failure_msg(self, message: str) -> str:
        return f"Error: {message}"

    def run(
        self,
        prompt: str = "",
        output_dir: str = "",
        size: str = "1920x1080",
        negative_prompt: Optional[str] = None,
        timeout: int = 60,
        **kwargs: Any,
    ) -> str:
        """执行图片生成。整个方法被顶层 try-except 包裹，确保任何异常都不会向上冒泡。"""
        try:
            return self._do_run(prompt, output_dir, size, negative_prompt, timeout)
        except Exception as exc:  # pylint: disable=broad-except
            # 终极兜底：无论什么原因，绝不让图片生成崩溃 pipeline
            import logging

            logging.getLogger(__name__).warning(
                "图片生成未预期异常（已安全跳过）: %s", exc, exc_info=True
            )
            return self._build_failure_msg(
                f"图片生成遇到未预期错误，已跳过（不影响后续流程）: {exc}"
            )

    def _do_run(
        self,
        prompt: str,
        output_dir: str,
        size: str = "1920x1080",
        negative_prompt: Optional[str] = None,
        timeout: int = 60,
    ) -> str:
        """图片生成的实际逻辑。"""
        if requests is None:
            return self._build_failure_msg(
                "未安装 requests 库，请先安装 requests>=2.31.0"
            )

        # 构造请求体
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "size": size,
            "response_format": "b64_json",
            "n": 1,
        }
        if self.model:
            payload["model"] = self.model
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if self.steps is not None:
            payload["steps"] = self.steps
        if self.guidance_scale is not None:
            payload["guidance_scale"] = self.guidance_scale

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{self.base_url}/images/generations",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        except Exception as exc:  # pylint: disable=broad-except
            return self._build_failure_msg(f"图片生成请求失败: {exc}")

        if response.status_code != 200:
            try:
                detail = response.json().get("detail", response.text[:500])
            except Exception:  # pylint: disable=broad-except
                detail = response.text[:500]
            return self._build_failure_msg(
                f"图片生成接口返回异常: HTTP {response.status_code} / {detail}"
            )

        try:
            resp_json = response.json()
        except Exception as exc:  # pylint: disable=broad-except
            return self._build_failure_msg(f"响应解析失败: {exc}")

        data_list = resp_json.get("data") or []
        if not data_list:
            return self._build_failure_msg("图片生成接口未返回可用图像数据")

        item = data_list[0]
        b64_json = item.get("b64_json")
        url = item.get("url")

        # 优先使用 b64_json，否则下载 url
        if b64_json:
            import base64

            try:
                image_bytes = base64.b64decode(b64_json)
            except Exception as exc:  # pylint: disable=broad-except
                return self._build_failure_msg(f"图片 base64 解码失败: {exc}")
        elif url:
            try:
                img_resp = requests.get(url, timeout=timeout)
                img_resp.raise_for_status()
                image_bytes = img_resp.content
            except Exception as exc:  # pylint: disable=broad-except
                return self._build_failure_msg(f"下载生成图片失败: {exc}")
        else:
            return self._build_failure_msg("响应中既无 b64_json 也无 url")

        # 落盘
        out_dir = Path(output_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        image_hash = self._content_hash(image_bytes)
        image_path = out_dir / f"{image_hash}.png"

        if not image_path.exists():
            try:
                image_path.write_bytes(image_bytes)
                self._write_meta(
                    image_path,
                    {
                        "image_hash": image_hash,
                        "image_path": str(image_path),
                        "prompt": prompt,
                        "negative_prompt": negative_prompt,
                        "size": size,
                        "steps": self.steps,
                        "guidance_scale": self.guidance_scale,
                        "model": self.model,
                        "base_url": self.base_url,
                        "created_at": time.strftime(
                            "%Y-%m-%d %H:%M:%S", time.localtime()
                        ),
                    },
                )
            except Exception as exc:  # pylint: disable=broad-except
                return self._build_failure_msg(f"图片落盘失败: {exc}")

        return f"图片生成成功，路径：{str(image_path)}"


__all__ = ["OpenAIImageGenTool"]


if __name__ == "__main__":
    from dotenv import load_dotenv
    import os

    load_dotenv()

    tool = OpenAIImageGenTool(
        api_key=os.getenv("IMG_API_KEY"),
        base_url=os.getenv("IMG_BASE_URL"),
        model=os.getenv("IMG_MODEL"),
    )

    print(tool(prompt="a cute cat.", output_dir="."))
