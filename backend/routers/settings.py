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
        return {"ok": False, "error": str(e)}


@router.post("/test-image")
def test_image_gen(user_id: str = Depends(get_current_user)):
    """测试图像生成 API 是否可用（真正生成一张图片并返回 base64 供前端展示）。"""
    try:
        import base64

        # 额度检查
        check_and_consume(user_id, "image")

        from database import get_setting
        import os

        base_url = get_setting(user_id, "img_base_url") or os.getenv("IMG_BASE_URL", "")
        api_key = get_setting(user_id, "img_api_key") or os.getenv("IMG_API_KEY", "")
        model = get_setting(user_id, "img_model") or os.getenv("IMG_MODEL", "")
        if not base_url:
            return {"ok": False, "error": "未配置图像生成 Base URL"}
        if not api_key:
            return {"ok": False, "error": "未配置图像生成 API Key"}

        try:
            import requests as _requests
        except ImportError:
            return {"ok": False, "error": "requests 库未安装"}

        # 构造最小请求体，生成一张小尺寸测试图片
        payload = {
            "prompt": "A beautiful sunset over a calm ocean",
            "size": "512x512",
            "response_format": "b64_json",
            "n": 1,
        }
        if model:
            payload["model"] = model

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        resp = _requests.post(
            f"{base_url.rstrip('/')}/images/generations",
            json=payload,
            headers=headers,
            timeout=120,
        )

        if resp.status_code != 200:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text[:300])
            except Exception:
                detail = resp.text[:300]
            return {"ok": False, "error": f"HTTP {resp.status_code}: {detail}"}

        resp_json = resp.json()
        data_list = resp_json.get("data") or []
        if not data_list:
            return {"ok": False, "error": "接口未返回图像数据"}

        item = data_list[0]
        b64_data = item.get("b64_json")
        url = item.get("url")

        # 优先使用 b64_json，否则下载 url 再转 base64
        if b64_data:
            image_b64 = b64_data
        elif url:
            try:
                img_resp = _requests.get(url, timeout=60)
                img_resp.raise_for_status()
                image_b64 = base64.b64encode(img_resp.content).decode("utf-8")
            except Exception as dl_err:
                return {"ok": False, "error": f"图片下载失败: {dl_err}"}
        else:
            return {"ok": False, "error": "接口返回数据中无 b64_json 或 url 字段"}

        return {
            "ok": True,
            "reply": "图像生成成功，API 配置正确",
            "image": f"data:image/png;base64,{image_b64}",
        }

    except Exception as e:  # pylint: disable=broad-except
        return {"ok": False, "error": str(e)}


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
        return {"ok": False, "error": str(e)}
