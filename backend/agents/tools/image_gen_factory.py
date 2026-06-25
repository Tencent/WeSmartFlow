#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图像生成工具工厂。

统一收集 `OpenAIImageGenTool` 等图像生成工具的构建逻辑：
- 从用户设置 / 环境变量读取 api_key / base_url / model
- 容错（设置读取失败时回退到环境变量默认值）
- 统一日志

供 services / agents 等多处复用，避免重复实现。
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from agent_core.tool.openai_image_gen import OpenAIImageGenTool
from agent_core.tool.qwen_image_gen import QwenImageGenTool

logger = logging.getLogger(__name__)

# 默认值（与原各处实现保持一致）
_DEFAULT_API_KEY = "any"
_DEFAULT_BASE_URL = "http://localhost:8080/v1"


def build_image_gen_tool(
    user_id,
    before_call_hook: Optional[Callable] = None,
) -> OpenAIImageGenTool:
    """构建图像生成工具实例（OpenAI 兼容接口）。

    优先从用户设置（database.get_setting）读取，失败或未设置时回退到环境变量，
    最后回退到内置默认值。

    Args:
        user_id: 当前用户 ID，用于读取个性化设置。
        before_call_hook: 工具执行前的钩子（如额度检查），传 None 表示不限制。

    Returns:
        已配置好的 OpenAIImageGenTool 实例。
    """
    try:
        from database import get_setting

        api_key = get_setting(user_id, "img_api_key") or os.getenv(
            "IMG_API_KEY", _DEFAULT_API_KEY
        )
        base_url = get_setting(user_id, "img_base_url") or os.getenv(
            "IMG_BASE_URL", _DEFAULT_BASE_URL
        )
        model = get_setting(user_id, "img_model") or os.getenv("IMG_MODEL") or None
    except Exception as e:  # pylint: disable=broad-except
        logger.warning(
            "图片生成配置读取失败（将使用默认值，图片功能可能不可用）: %s", e
        )
        api_key = os.getenv("IMG_API_KEY", _DEFAULT_API_KEY)
        base_url = os.getenv("IMG_BASE_URL", _DEFAULT_BASE_URL)
        model = os.getenv("IMG_MODEL") or None

    return QwenImageGenTool(
        api_key=api_key,
        base_url=base_url,
        model=model,
        before_call_hook=before_call_hook,
    )


__all__ = ["build_image_gen_tool"]
