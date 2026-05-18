"""Web 搜索与抓取工具集合。

包含：
- WebFetch        — 抓取 URL 页面内容，提取为可读文本或 Markdown
- WebSearch       — Google 搜索（基于 SerpAPI）
- TavilySearch    — Tavily AI 搜索
- ArxivSearch     — arXiv 论文搜索
- DuckDuckGoSearch — DuckDuckGo 免费搜索
"""

from __future__ import annotations

import html
import json
import os
import re
from typing import Any, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

from .base import BaseTool

load_dotenv()

# ============================================================
# WebFetch
# ============================================================

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5


def _strip_tags(text: str) -> str:
    """移除 HTML 标签并解码实体。"""
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """规范化空白字符。"""
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """校验 URL：必须是 http(s) 且包含有效域名。"""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False, f"仅支持 http/https，当前协议: '{p.scheme or '无'}'"
        if not p.netloc:
            return False, "缺少域名"
        return True, ""
    except Exception as e:  # pylint: disable=broad-except
        return False, str(e)


def _to_markdown(raw_html: str) -> str:
    """将 HTML 转换为 Markdown 格式文本。"""
    text = re.sub(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
        lambda m: f"[{_strip_tags(m[2])}]({m[1]})",
        raw_html,
        flags=re.I,
    )
    text = re.sub(
        r"<h([1-6])[^>]*>([\s\S]*?)</h\1>",
        lambda m: f"\n{'#' * int(m[1])} {_strip_tags(m[2])}\n",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"<li[^>]*>([\s\S]*?)</li>",
        lambda m: f"\n- {_strip_tags(m[1])}",
        text,
        flags=re.I,
    )
    text = re.sub(r"</(p|div|section|article)>", "\n\n", text, flags=re.I)
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
    return _normalize(_strip_tags(text))


class WebFetch(BaseTool):
    """抓取指定 URL 的页面内容，并提取为可读文本或 Markdown。"""

    name = "web_fetch"
    description = "抓取指定 URL 的页面内容，将 HTML 提取为可读文本或 Markdown。"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要抓取的目标 URL"},
            "extract_mode": {
                "type": "string",
                "description": "提取模式：markdown（默认）或 text",
            },
            "max_chars": {
                "type": "integer",
                "description": "最大返回字符数，默认 50000",
            },
        },
        "required": ["url"],
    }

    def __init__(self, max_chars: int = 50000, proxy: Optional[str] = None):
        self.max_chars = max_chars
        self.proxy = proxy or os.getenv("FETCH_PROXY", "")
        super().__init__()

    def run(
        self,
        url: str,
        extract_mode: str = "markdown",
        max_chars: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        try:
            import trafilatura
        except ImportError:
            return json.dumps(
                {
                    "error": "缺少依赖 trafilatura，请执行: pip install trafilatura",
                    "url": url,
                },
                ensure_ascii=False,
            )

        try:
            import requests
        except ImportError:
            return json.dumps(
                {
                    "error": "缺少依赖 requests，请执行: pip install requests",
                    "url": url,
                },
                ensure_ascii=False,
            )

        limit = max_chars or self.max_chars
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps(
                {"error": f"URL 校验失败: {error_msg}", "url": url}, ensure_ascii=False
            )

        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None

        try:
            s = requests.Session()
            s.max_redirects = MAX_REDIRECTS
            resp = s.get(
                url,
                headers={"User-Agent": USER_AGENT},
                proxies=proxies,
                timeout=30,
                allow_redirects=True,
            )
            resp.raise_for_status()

            ctype = resp.headers.get("content-type", "")
            if "application/json" in ctype:
                text = json.dumps(resp.json(), indent=2, ensure_ascii=False)
            elif "text/html" in ctype or resp.text[:256].lower().startswith(
                ("<!doctype", "<html")
            ):
                output_format = "markdown" if extract_mode == "markdown" else "txt"
                text = trafilatura.extract(
                    resp.text,
                    output_format=output_format,
                    include_links=False,
                    include_tables=True,
                    include_images=False,
                    favor_recall=True,
                )
                if not text:
                    text = (
                        _to_markdown(resp.text)
                        if extract_mode == "markdown"
                        else _strip_tags(resp.text)
                    )
            else:
                text = resp.text

            if len(text) > limit:
                text = text[:limit]
            return text

        except requests.exceptions.ProxyError:
            return f"error: 代理错误, url: {url}"
        except requests.exceptions.Timeout:
            return f"error: 请求超时, url: {url}"
        except Exception as e:  # pylint: disable=broad-except
            return f"error: {str(e)}, url: {url}"


# ============================================================
# TavilySearch
# ============================================================


class TavilySearch(BaseTool):
    """Tavily 搜索工具，专为 AI Agent 设计，返回经过 AI 提炼的搜索结果。需要 TAVILY_API_KEY。"""

    name = "tavily_search"
    description = (
        "使用 Tavily 执行网络搜索，返回经过 AI 提炼的高质量搜索结果。"
        "支持直接返回答案摘要，适合需要准确信息的 Agent 场景。需要配置 TAVILY_API_KEY。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词或问题"},
            "num_results": {
                "type": "integer",
                "description": "返回结果数量，默认为 5，最大为 10",
            },
            "search_depth": {
                "type": "string",
                "description": "搜索深度：'basic'（快速，默认）或 'advanced'（更深入，消耗更多额度）",
            },
            "include_answer": {
                "type": "boolean",
                "description": "是否在结果中包含 AI 生成的直接答案摘要，默认为 true",
            },
        },
        "required": ["query"],
    }

    def __init__(self, api_key: str | None = None, before_call_hook=None):
        self._api_key = api_key
        super().__init__(before_call_hook=before_call_hook)

    def _get_api_key(self) -> str:
        """优先使用构造时传入的 api_key，回退到环境变量。"""
        if self._api_key:
            return self._api_key
        return os.getenv("TAVILY_API_KEY", "")

    def run(
        self,
        query: str,
        num_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = True,
        **kwargs: Any,
    ) -> str:
        api_key = self._get_api_key()
        if not api_key:
            return "未配置 TAVILY_API_KEY，请在设置页面填写或在 .env 文件中添加 TAVILY_API_KEY=tvly-xxxxx"

        try:
            from tavily import TavilyClient
        except ImportError:  # pylint: disable=broad-except
            return "未安装 tavily-python 库，请运行 pip install tavily-python"

        try:
            client = TavilyClient(api_key=api_key)
            response = client.search(
                query=query,
                search_depth=search_depth,
                max_results=num_results,
                include_answer=include_answer,
            )

            parts = []
            answer = response.get("answer")
            if answer:
                parts.append(f"【AI 答案摘要】\n{answer}")

            for i, r in enumerate(response.get("results", []), 1):
                parts.append(
                    f"[{i}] {r.get('title', '无标题')}\n"
                    f"    {r.get('content', '无摘要')}\n"
                    f"    链接: {r.get('url', '')}"
                )

            return "\n\n".join(parts) if parts else "未找到相关信息"

        except Exception as e:  # pylint: disable=broad-except
            return f"搜索异常: {e}"


# ============================================================
# ArxivSearch
# ============================================================


class ArxivSearch(BaseTool):
    """arXiv 论文搜索工具。"""

    name = "arxiv_search"
    description = "搜索 arXiv 论文，返回论文标题、摘要、作者、发表日期和链接。搜索关键词使用英文效果最佳。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词，建议使用英文"},
            "max_results": {"type": "integer", "description": "返回论文数量，默认为 3"},
        },
        "required": ["query"],
    }

    def __init__(self):
        super().__init__()

    def run(self, query: str, max_results: int = 3, **kwargs: Any) -> str:
        try:
            import arxiv
        except ImportError:  # pylint: disable=broad-except
            return "未安装 arxiv 库，请运行 pip install arxiv"

        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
            )

            parts = []
            for i, paper in enumerate(search.results(), 1):
                authors = ", ".join([a.name for a in paper.authors[:3]])
                summary = paper.summary[:500]
                published = paper.published.strftime("%Y-%m-%d")
                parts.append(
                    f"[论文{i}] {paper.title}\n"
                    f"  作者: {authors}\n"
                    f"  发表: {published}\n"
                    f"  摘要: {summary}\n"
                    f"  链接: {paper.entry_id}"
                )

            return "\n\n".join(parts) if parts else "未找到相关论文"

        except Exception as e:  # pylint: disable=broad-except
            return f"arXiv 搜索异常: {e}"


__all__ = [
    "WebFetch",
    "TavilySearch",
    "ArxivSearch",
]

if __name__ == "__main__":
    web_fetch_tool = WebFetch()
    tavily_search_tool = TavilySearch()
    arxiv_search_tool = ArxivSearch()

    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    QUERY = "2024年诺贝尔物理学奖"

    # ── WebFetch ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("【WebFetch】抓取 arxiv 页面")
    print("=" * 60)
    fetcher = WebFetch(max_chars=2000)
    print(fetcher.run("https://arxiv.org/abs/2603.14770v1"))

    # ── TavilySearch ─────────────────────────────────────────
    print("\n" + "=" * 60)
    print("【TavilySearch】Tavily AI 搜索")
    print("=" * 60)
    print(tavily_search_tool.run(QUERY, num_results=3, include_answer=True))

    # ── ArxivSearch ───────────────────────────────────────────
    print("\n" + "=" * 60)
    print("【ArxivSearch】arXiv 论文搜索")
    print("=" * 60)
    print(arxiv_search_tool.run("deep learning 2024", max_results=2))
