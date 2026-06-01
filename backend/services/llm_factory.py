"""
LLM 工厂：根据数据库 settings 表（或环境变量 fallback）创建 LLM 实例

优先使用用户配置的 OpenAI 兼容接口，否则 fallback 到环境变量 LLM_API_KEY。

额度管理通过 before_call hook 注入到需要限制的 LLM 实例中。
"""

from __future__ import annotations

import os

from agent_core.llm import BaseLLM
from agent_core.llm.openai_llm import OpenAILLM
from database import get_setting


def _get_cfg(user_id: str, key: str, env_fallback: str = "") -> str:
    """从 settings 表读取指定用户的配置，读取失败则 fallback 到环境变量。"""
    try:
        val = get_setting(user_id, key)
        if val:  # 非空才使用用户配置
            return val
    except Exception:  # pylint: disable=broad-except
        pass

    return os.getenv(env_fallback, "")


def _make_llm_quota_hook(user_id: str):
    """创建 LLM 额度检查 hook，每次 LLM 调用前自动触发。"""

    def _hook():
        from services.quota import check_and_consume

        check_and_consume(user_id, "llm")

    return _hook


def create_openai_llm(
    user_id: str,
    *,
    api_key: str,
    base_url: str = "",
    model: str = "",
    with_quota: bool = True,
) -> OpenAILLM:
    """创建 OpenAI 兼容 LLM 实例。

    Args:
        user_id: 用户 ID
        api_key: OpenAI API Key（必传）。
        base_url: OpenAI 兼容 base URL，为空则使用 SDK 默认值。
        model: 模型名称，为空则使用 SDK 默认值。
        with_quota: 是否注入免费额度检查 hook（默认 True）。
    """
    if not api_key:
        raise RuntimeError(
            "未配置 LLM API Key。请在设置页面填写，或在 .env 中设置 LLM_API_KEY。"
        )
    return OpenAILLM(
        model_name=model or None,
        api_key=api_key,
        base_url=base_url or None,
        before_call=_make_llm_quota_hook(user_id) if with_quota else None,
    )


def get_llm(user_id: str) -> BaseLLM:
    """每次调用都从数据库/环境变量读取指定用户的最新配置，确保设置页修改后立即生效。

    优先级：
      1. 用户在设置页配置了自己的 OpenAI key → 使用 OpenAI（不限额）
      2. 环境变量有 LLM_API_KEY → 使用 OpenAI（消耗免费额度）
      3. 都没有 → 报错

    用户自配 OpenAI key 不限额；
    只有 fallback 到平台 OpenAI key 时才会消耗免费对话额度。
    """
    # 一次性读取用户配置
    user_key = _get_cfg(user_id, "llm_api_key", "")
    base_url = _get_cfg(user_id, "llm_base_url", "")
    model = _get_cfg(user_id, "llm_model", "")

    # 用户自定义的 OpenAI key 优先, 不消耗免费额度
    if user_key:
        # 检查必须的用户配置项是否齐全
        if not base_url or not model:
            raise RuntimeError(
                "用户配置的 LLM 不完整。请确保同时设置了 llm_api_key, llm_base_url 和 llm_model。"
            )

        return create_openai_llm(
            user_id, api_key=user_key, base_url=base_url, model=model, with_quota=False
        )

    # 环境变量 LLM_API_KEY, 消耗免费额度
    env_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "")
    model = os.getenv("LLM_MODEL", "")
    if env_key:
        # 检查必须的环境变量是否齐全
        if not base_url or not model:
            raise RuntimeError(
                "环境变量配置的 LLM 不完整。请确保同时设置了 LLM_API_KEY, LLM_BASE_URL 和 LLM_MODEL。"
            )

        return create_openai_llm(
            user_id, api_key=env_key, base_url=base_url, model=model, with_quota=True
        )

    raise RuntimeError("未配置任何 LLM 服务。请在 .env 中设置 LLM_API_KEY。")
