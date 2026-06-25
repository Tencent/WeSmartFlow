"""
系统设置路由
GET  /api/settings               → 返回所有配置项（敏感字段脱敏）
GET  /api/settings/quota         → 查询用户剩余免费次数
POST /api/settings               → 批量保存配置项
POST /api/settings/test          → 测试当前 LLM 配置是否可用
POST /api/settings/test-tavily   → 测试 Tavily API Key 是否可用
POST /api/settings/test-image    → 测试图像生成 API 是否可用
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database import get_all_settings, set_settings_batch
from dependencies import get_current_user
from services.quota import check_and_consume, get_usage
from utils.log_safe import safe_log
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 敏感字段：返回给前端时脱敏
_SENSITIVE_KEYS = {"llm_api_key", "tavily_api_key", "img_api_key"}


def _mask(key: str, value: str) -> str:
    """敏感字段只返回前4位 + *** 或空字符串。"""
    if key not in _SENSITIVE_KEYS or not value:
        return value
    return value[:4] + "***" if len(value) > 4 else "***"


class SettingsSaveRequest(BaseModel):
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    tavily_api_key: str | None = None
    img_api_key: str | None = None
    img_base_url: str | None = None
    img_model: str | None = None


@router.get("/quota")
def get_quota(user_id: str = Depends(get_current_user)):
    """查询当前用户各类别的剩余免费次数。

    返回示例:
    {
        "llm":    {"used": 5, "limit": 400, "remaining": 395, "is_platform": true},
        "search": {"used": 2, "limit": 50,  "remaining": 48,  "is_platform": true},
        "image":  {"used": 0, "limit": -1,  "remaining": -1,  "is_platform": false}
    }
    其中 limit=-1 / remaining=-1 表示用户使用自己的 Key，不限次数。
    """
    usage = get_usage(user_id)
    result = {}
    for cat, info in usage.items():
        limit = info["limit"]
        used = info["used"]
        remaining = max(limit - used, 0) if limit >= 0 else -1
        result[cat] = {
            "used": used,
            "limit": limit,
            "remaining": remaining,
            "is_platform": info["is_platform"],
        }
    return result


@router.get("")
def get_settings(user_id: str = Depends(get_current_user)):
    """返回当前用户的所有配置项，敏感字段脱敏。"""
    raw = get_all_settings(user_id)
    return {k: _mask(k, v) for k, v in raw.items()}


@router.post("")
def save_settings(body: SettingsSaveRequest, user_id: str = Depends(get_current_user)):
    """批量保存当前用户的配置项，None 字段跳过（不覆盖）。"""
    updates: dict[str, str] = {}
    for key, value in body.model_dump().items():
        if value is not None:
            updates[key] = value
    if updates:
        set_settings_batch(user_id, updates)
    return {"ok": True, "updated": list(updates.keys())}


@router.post("/test")
def test_llm(user_id: str = Depends(get_current_user)):
    """测试当前 LLM 配置是否可用（发送一条最小请求）。"""
    try:
        from services.llm_factory import get_llm

        llm = get_llm(user_id)
        resp = llm.think(
            [{"role": "user", "content": "reply with the single word: ok"}],
            config={"max_tokens": 10},
        )
        # 检查 finish_reason / is_error，避免把错误内容当成成功回复
        if resp.finish_reason == "error" or getattr(resp, "is_error", False):
            error_msg = (
                resp.metadata.get("error_message", resp.content)
                if resp.metadata
                else resp.content
            )
            return {"ok": False, "error": error_msg}
        return {"ok": True, "reply": resp.content.strip()}
    except Exception as e:  # pylint: disable=broad-except
        logger.exception("LLM 测试异常 (user=%s), error: %s", safe_log(user_id), str(e))
        return {"ok": False, "error": "LLM 测试失败"}


@router.post("/test-image")
def test_image_gen(user_id: str = Depends(get_current_user)):
    """测试图像生成 API 是否可用（真正生成一张图片并返回 base64 供前端展示）。

    复用 `build_image_gen_tool` 工厂，确保测试链路与实际生成链路完全一致。
    """
    try:
        import base64
        import os
        import tempfile
        from pathlib import Path

        from database import get_setting
        from agents.tools.image_gen_factory import build_image_gen_tool

        # 前置校验：在调工具前给出更友好的错误
        base_url = get_setting(user_id, "img_base_url") or os.getenv("IMG_BASE_URL", "")
        api_key = get_setting(user_id, "img_api_key") or os.getenv("IMG_API_KEY", "")
        if not base_url:
            return {"ok": False, "error": "未配置图像生成 Base URL"}
        if not api_key:
            return {"ok": False, "error": "未配置图像生成 API Key"}

        # 额度检查
        check_and_consume(user_id, "image")

        # 构建工具并生成测试图片到临时目录
        tool = build_image_gen_tool(user_id, before_call_hook=None)
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = tool(
                prompt="A beautiful sunset over a calm ocean",
                output_dir=tmp_dir,
                size="512*512",
                timeout=120,
            )

            # 工具失败时返回的是 "Error: ..." 字符串
            if isinstance(result, str) and result.startswith("Error:"):
                return {"ok": False, "error": result[len("Error:") :].strip()}

            # 成功返回格式："图片生成成功，路径：<path>"
            prefix = "图片生成成功，路径："
            if not (isinstance(result, str) and prefix in result):
                return {"ok": False, "error": f"图像工具返回异常: {result}"}

            image_path = Path(result.split(prefix, 1)[1].strip())
            if not image_path.exists():
                return {"ok": False, "error": f"图片文件不存在: {image_path}"}

            image_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")

        return {
            "ok": True,
            "reply": "图像生成成功，API 配置正确",
            "image": f"data:image/png;base64,{image_b64}",
        }

    except Exception as e:  # pylint: disable=broad-except
        logger.exception(
            "图像生成测试异常 (user=%s), error: %s", safe_log(user_id), str(e)
        )
        return {"ok": False, "error": "图像生成测试失败"}


@router.post("/test-tavily")
def test_tavily(user_id: str = Depends(get_current_user)):
    """测试 Tavily API Key 是否可用（发送一条最小搜索请求）。"""
    try:
        # 额度检查
        check_and_consume(user_id, "search")

        from database import get_setting
        import os

        api_key = get_setting(user_id, "tavily_api_key") or os.getenv(
            "TAVILY_API_KEY", ""
        )
        if not api_key:
            return {"ok": False, "error": "未配置 Tavily API Key"}
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        result = client.search("test", max_results=1)
        return {
            "ok": True,
            "reply": f"连接成功，返回 {len(result.get('results', []))} 条结果",
        }
    except ImportError:
        return {
            "ok": False,
            "error": "tavily-python 未安装，请运行 pip install tavily-python",
        }
    except Exception as e:  # pylint: disable=broad-except
        logger.exception(
            "Tavily API 测试异常 (user=%s), error: %s", safe_log(user_id), str(e)
        )
        return {"ok": False, "error": "Tavily API 测试失败"}
