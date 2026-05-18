"""
LLM 工厂：根据数据库 settings 表（或环境变量 fallback）创建 LLM 实例

额度管理通过 before_call hook 自动注入到 LLM 实例中，
每次 LLM 真正调用 API 时自动触发额度检查，无需业务层手动调用。
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


def create_openai_llm(user_id: str) -> OpenAILLM:
    """根据当前用户的 settings 创建 OpenAI 兼容 LLM 实例（自动注入额度 hook）。"""
    api_key = _get_cfg(user_id, "llm_api_key", "LLM_API_KEY")
    base_url = _get_cfg(user_id, "llm_base_url", "LLM_BASE_URL")
    model = _get_cfg(user_id, "llm_model", "LLM_MODEL")

    if not api_key:
        raise RuntimeError(
            "未配置 LLM API Key。请在设置页面填写，或在 .env 中设置 LLM_API_KEY。"
        )
    return OpenAILLM(
        model_name=model or None,
        api_key=api_key,
        base_url=base_url or None,
        before_call=_make_llm_quota_hook(user_id),
    )


def get_llm(user_id: str) -> BaseLLM:
    """每次调用都从数据库/环境变量读取指定用户的最新配置，确保设置页修改后立即生效。

    返回的 LLM 实例已自动注入额度检查 hook，业务层无需手动调用 check_and_consume。
    """
    return create_openai_llm(user_id)
