"""
LLM 工厂：根据数据库 settings 表（或环境变量 fallback）创建 LLM 实例
"""

from __future__ import annotations


from agent_core.llm import BaseLLM
from agent_core.llm.openai_llm import OpenAILLM


def _get_cfg(key: str, env_fallback: str = "") -> str:
    """从 settings 表读取配置，读取失败则 fallback 到环境变量。"""
    try:
        from database import get_setting

        val = get_setting(key)
        if val is not None:
            return val
    except Exception:  # pylint: disable=broad-except
        pass
    import os

    return os.getenv(env_fallback, "")


def create_openai_llm() -> OpenAILLM:
    """根据当前 settings 创建 OpenAI 兼容 LLM 实例。"""
    api_key = _get_cfg("llm_api_key", "LLM_API_KEY")
    base_url = _get_cfg("llm_base_url", "LLM_BASE_URL")
    model = _get_cfg("llm_model", "LLM_MODEL")

    if not api_key:
        raise RuntimeError(
            "未配置 LLM API Key。请在设置页面填写，或在 backend/.env 中设置 LLM_API_KEY。"
        )
    return OpenAILLM(
        model_name=model or None,
        api_key=api_key,
        base_url=base_url or None,
    )


def get_llm() -> BaseLLM:
    """每次调用都从数据库读取最新配置，确保设置页修改后立即生效。
    默认使用 iChat 模型。"""
    return create_openai_llm()
