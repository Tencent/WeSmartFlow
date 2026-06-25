#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通义千问图像生成工具（DashScope multimodal-generation API）。

调用阿里云 DashScope qwen-image-2.0-pro 接口，
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


class QwenImageGenTool(BaseTool):
    """调用通义千问 qwen-image-2.0-pro 生成图片，并落盘到指定目录。"""

    name = "qwen_image_generate"
    description = (
        "调用阿里云通义千问图像生成接口，"
        "根据文本提示词生成高质量图片并保存到指定目录。"
        "支持指定图像尺寸、负向提示词、是否开启提示词扩写等参数。"
        "调用成功后返回图片的本地绝对路径。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "图像描述提示词，支持中英文，详细描述画面内容。",
            },
            "output_dir": {
                "type": "string",
                "description": "图片输出目录路径，图片将保存到该目录下。",
            },
            "size": {
                "type": "string",
                "description": (
                    "图像尺寸，格式 W*H。推荐值：\n"
                    "  • 1024*1024（1:1，方图，通用插图）\n"
                    "  • 1280*720（16:9，横图，幻灯片首选）\n"
                    "  • 720*1280（9:16，竖图，海报/手机壁纸）\n"
                    "  • 2048*2048（1:1，高清方图）\n"
                    "  • 1024*768（4:3，横图，场景/风景）\n"
                    "默认 1024*1024。"
                ),
            },
            "negative_prompt": {
                "type": "string",
                "description": (
                    "负向提示词，描述不希望出现的内容，"
                    "如：低分辨率，低画质，肢体畸形，手指畸形。"
                ),
            },
            "prompt_extend": {
                "type": "boolean",
                "description": "是否开启提示词自动扩写，默认 true，可提升画面丰富度。",
            },
            "watermark": {
                "type": "boolean",
                "description": "是否在图片上添加水印，默认 false。",
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
        api_key: str = "",
        base_url: str = "https://dashscope.aliyuncs.com/api/v1",
        model: str = "qwen-image-2.0-pro",
        before_call_hook=None,
    ):
        """
        Args:
            api_key:          DashScope API Key。
            base_url:        服务根地址，默认 https://dashscope.aliyuncs.com/api/v1。
            model:           模型名称，默认 qwen-image-2.0-pro。
            before_call_hook: 执行前回调（如额度检查）。
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
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
        size: str = "1024*1024",
        negative_prompt: Optional[str] = None,
        prompt_extend: bool = True,
        watermark: bool = False,
        timeout: int = 300,
        **kwargs: Any,
    ) -> str:
        """执行图片生成。整个方法被顶层 try-except 包裹，确保任何异常都不会向上冒泡。"""
        try:
            return self._do_run(
                prompt,
                output_dir,
                size,
                negative_prompt,
                prompt_extend,
                watermark,
                timeout,
            )
        except Exception as exc:  # pylint: disable=broad-except
            import logging

            logging.getLogger(__name__).warning(
                "Qwen 图片生成未预期异常（已安全跳过）: %s", exc, exc_info=True
            )
            return self._build_failure_msg(
                f"图片生成遇到未预期错误，已跳过（不影响后续流程）: {exc}"
            )

    def _do_run(
        self,
        prompt: str,
        output_dir: str,
        size: str = "1024*1024",
        negative_prompt: Optional[str] = None,
        prompt_extend: bool = True,
        watermark: bool = False,
        timeout: int = 300,
    ) -> str:
        """图片生成的实际逻辑。"""
        if requests is None:
            return self._build_failure_msg(
                "未安装 requests 库，请先安装 requests>=2.31.0"
            )

        if not self.api_key:
            return self._build_failure_msg(
                "未提供 DashScope API Key，请在构造时传入 api_key。"
            )

        # ── 将平铺的参数组装成 DashScope API 所需的嵌套结构 ──
        payload: Dict[str, Any] = {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ]
            },
            "parameters": {
                "size": size,
                "prompt_extend": prompt_extend,
                "watermark": watermark,
            },
        }
        if negative_prompt:
            payload["parameters"]["negative_prompt"] = negative_prompt

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{self.base_url}",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        except Exception as exc:  # pylint: disable=broad-except
            return self._build_failure_msg(f"图片生成请求失败: {exc}")

        if response.status_code != 200:
            try:
                detail = response.json()
            except Exception:  # pylint: disable=broad-except
                detail = response.text[:500]
            return self._build_failure_msg(
                f"图片生成接口返回异常: HTTP {response.status_code} / {detail}"
            )

        try:
            resp_json = response.json()
        except Exception as exc:  # pylint: disable=broad-except
            return self._build_failure_msg(f"响应解析失败: {exc}")

        # DashScope 响应结构：output.choices[0].message.content[0].image
        try:
            content = resp_json["output"]["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return self._build_failure_msg(
                f"响应结构不符合预期: {json.dumps(resp_json, ensure_ascii=False)[:300]}"
            )

        # content 是列表，找第一个含 image 的项
        image_url: Optional[str] = None
        for item in content:
            if isinstance(item, dict):
                image_url = item.get("image")
                if image_url:
                    break

        if not image_url:
            return self._build_failure_msg(
                f"响应中未找到图片 URL: {json.dumps(resp_json, ensure_ascii=False)[:300]}"
            )

        # 下载图片
        try:
            img_resp = requests.get(image_url, timeout=timeout)
            img_resp.raise_for_status()
            image_bytes = img_resp.content
        except Exception as exc:  # pylint: disable=broad-except
            return self._build_failure_msg(f"下载生成图片失败: {exc}")

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
                        "prompt_extend": prompt_extend,
                        "watermark": watermark,
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


__all__ = ["QwenImageGenTool"]


if __name__ == "__main__":
    from dotenv import load_dotenv
    import os

    load_dotenv()

    tool = QwenImageGenTool(
        api_key=os.getenv("IMG_API_KEY"),
        base_url=os.getenv("IMG_BASE_URL"),
        model=os.getenv("IMG_MODEL"),
    )

    result = tool(
        prompt="冬日北京街景，两间中式商铺，檐下悬挂灯笼，鹅卵石路面。",
        output_dir=".",
        size="1024*1024",
        negative_prompt="低分辨率，低画质，肢体畸形",
        prompt_extend=True,
        watermark=False,
    )
    print(result)
