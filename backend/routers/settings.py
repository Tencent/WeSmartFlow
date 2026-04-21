"""
系统设置路由
GET  /api/settings               → 返回所有配置项（敏感字段脱敏）
POST /api/settings               → 批量保存配置项
POST /api/settings/test          → 测试当前 LLM 配置是否可用
POST /api/settings/test-tavily   → 测试 Tavily API Key 是否可用
POST /api/settings/validate-path → 校验路径是否合法可写
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from database import get_all_settings, set_settings_batch

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


@router.get("")
def get_settings():
    """返回所有配置项，敏感字段脱敏。"""
    raw = get_all_settings()
    return {k: _mask(k, v) for k, v in raw.items()}


@router.get("/raw")
def get_settings_raw():
    """返回所有配置项原始值（仅供后端内部调试，生产环境应鉴权）。"""
    return get_all_settings()


@router.post("")
def save_settings(body: SettingsSaveRequest):
    """批量保存配置项，None 字段跳过（不覆盖）。"""
    updates: dict[str, str] = {}
    for key, value in body.model_dump().items():
        if value is not None:
            updates[key] = value
    if updates:
        set_settings_batch(updates)
    return {"ok": True, "updated": list(updates.keys())}


@router.post("/test")
def test_llm():
    """测试当前 LLM 配置是否可用（发送一条最小请求）。"""
    try:
        from services.llm_factory import get_llm

        llm = get_llm()
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
def test_image_gen():
    """测试图像生成 API 是否可用（请求 /health 端点）。"""
    try:
        from database import get_setting

        base_url = get_setting("img_base_url") or ""
        if not base_url:
            return {"ok": False, "error": "未配置图像生成 Base URL"}
        try:
            import requests as _requests
        except ImportError:
            return {"ok": False, "error": "requests 库未安装"}
        # 去掉末尾的 /v1 等路径，取服务根地址
        import re

        root_url = re.sub(r"/v\d+/?$", "", base_url.rstrip("/"))
        resp = _requests.get(f"{root_url}/health", timeout=10)
        if resp.status_code == 200:
            return {"ok": True, "reply": "连接成功，图像生成服务可用"}
        else:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:  # pylint: disable=broad-except
        return {"ok": False, "error": str(e)}


@router.post("/test-tavily")
def test_tavily():
    """测试 Tavily API Key 是否可用（发送一条最小搜索请求）。"""
    try:
        from database import get_setting

        api_key = get_setting("tavily_api_key") or ""
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
