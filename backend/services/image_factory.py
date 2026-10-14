"""图像生成客户端工厂：装配额度拦截 + 记账 hook（与 llm_factory 同构）。

调用方（Agent 工具、测试接口）一律通过 :func:`get_image_gen` 获取
客户端实例——用量治理的单一收口。

后端选择：``IMG_PROVIDER`` 环境变量（``qwen`` / ``openai``，默认
``qwen``，与历史 ``build_image_gen_tool`` 行为一致）。配置读取优先
用户设置（img_api_key / img_base_url / img_model），回退环境变量。
"""

from __future__ import annotations

import logging
import os

from agent_core.hooks import hookwrapper, observe
from agent_core.tool.imagegen.base import BaseImageGen
from agent_core.tool.imagegen.openai import OpenAIImageGen
from agent_core.tool.imagegen.qwen import QwenImageGen
from services.provider_gateway import get_provider_gateway

logger = logging.getLogger(__name__)

# 空串 = 未配置：get_image_gen 会对空 api_key / base_url 提前抛 ValueError，
# 让上层（tool_catalog / generate_html_card / generate_card）走"不注册图片工具"的降级，
# 而不是把注定失败的客户端发给 Agent 在运行时报错（issue #62）。
_DEFAULT_API_KEY = ""
_DEFAULT_BASE_URL = ""


def _read_config(user_id: str) -> dict:
    """读取图像生成配置：用户设置优先，回退环境变量与内置默认值。"""
    try:
        from database import get_setting

        return {
            "api_key": get_setting(user_id, "img_api_key")
            or os.getenv("IMG_API_KEY", _DEFAULT_API_KEY),
            "base_url": get_setting(user_id, "img_base_url")
            or os.getenv("IMG_BASE_URL", _DEFAULT_BASE_URL),
            "model": get_setting(user_id, "img_model")
            or os.getenv("IMG_MODEL")
            or None,
        }
    except Exception:  # pylint: disable=broad-except
        logger.warning("图像生成配置读取失败（使用默认值）", exc_info=True)
        return {
            "api_key": os.getenv("IMG_API_KEY", _DEFAULT_API_KEY),
            "base_url": os.getenv("IMG_BASE_URL", _DEFAULT_BASE_URL),
            "model": os.getenv("IMG_MODEL") or None,
        }


def _attach_hooks(
    client: BaseImageGen,
    *,
    user_id: str,
    scene: str,
    with_quota: bool,
) -> BaseImageGen:
    """在 ``client.generate`` 外层装配额度拦截与记账 hook。"""

    from services.credit_quota import is_using_platform_key
    from services.pricing import calc_unit_credits

    platform_key = is_using_platform_key(user_id, "image")
    model = getattr(client, "model", "") or ""
    region = "singapore" if "-intl." in getattr(client, "base_url", "") else "beijing"

    # Instrument the raw provider call before the existing quota hook wraps it.
    # A quota denial therefore never appears as a provider incident.
    gateway = get_provider_gateway()
    profile = gateway.resolve(
        category="image",
        backend=client.backend,
        model=model,
        endpoint=getattr(client, "base_url", ""),
    )
    raw_generate = client.generate

    def _generate_with_policy(*args, **kwargs):
        kwargs.setdefault("timeout", int(profile.retry.timeout_seconds))
        return raw_generate(*args, **kwargs)

    client.generate = gateway.instrument_sync(  # type: ignore[method-assign]
        profile,
        "images.generate",
        _generate_with_policy,
        scene=scene,
        success=lambda result: bool(result),
    )
    client.provider_profile = profile  # type: ignore[attr-defined]

    def _pre(*_args, **_kwargs):
        from services.credit_quota import assert_available

        calc_unit_credits(
            "image", 1, model=model, provider=client.backend, region=region
        )
        assert_available(user_id, "image", platform_key=platform_key)

    def _post(cost_usd=None):
        from services.pricing import usd_to_credits
        from services.usage_meter import record_usage

        # 供应商返回真实成本（usage.cost_usd）时按实际记账，否则按单张估价
        record_usage(
            user_id,
            category="image",
            scene=scene,
            units=1,
            model=model,
            provider=client.backend,
            region=region,
            credits=usd_to_credits(cost_usd),
            counts_quota=platform_key,
        )

    pre = observe(_pre) if with_quota else None
    client.on_generated = lambda cost_usd=None: _post(cost_usd)
    client.generate = hookwrapper(client.generate, pre=pre)  # type: ignore[method-assign]
    return client


def get_image_gen(
    user_id: str,
    *,
    with_quota: bool = True,
    scene: str = "media",
) -> BaseImageGen:
    """构造图像生成客户端并挂治理 hook。

    Args:
        user_id:    用户 ID，用于读配置与额度归属。
        with_quota: 是否启用事前拦截（默认 True）；系统级调用传 False。
        scene:      用量归因场景（见 usage_meter.VALID_SCENES）。

    Raises:
        ValueError: 图像生成未配置（用户设置与环境变量均为空）。
                    调用方应捕获并降级（不注册图片工具），
                    与 routers.settings.test-image 的前置校验口径一致。
    """
    cfg = _read_config(user_id)
    if not cfg["api_key"] or not cfg["base_url"]:
        raise ValueError(
            "图像生成未配置：请先在用户设置或 .env 中配置 "
            "img_api_key/IMG_API_KEY 与 img_base_url/IMG_BASE_URL"
        )
    provider = os.getenv("IMG_PROVIDER", "qwen").strip().lower()

    if provider == "openai":
        client: BaseImageGen = OpenAIImageGen(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model=cfg["model"],
        )
    else:
        client = QwenImageGen(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model=cfg["model"] or "qwen-image-2.0-pro",
        )
    return _attach_hooks(client, user_id=user_id, scene=scene, with_quota=with_quota)


__all__ = ["get_image_gen"]
