"""Web 搜索与抓取工具集合。

包含：
- WebFetch        — 抓取 URL 页面内容，提取为可读文本或 Markdown
- WebSearch       — Google 搜索（基于 SerpAPI）
- TavilySearch    — Tavily AI 搜索
- ArxivSearch     — arXiv 论文搜索
- DuckDuckGoSearch — DuckDuckGo 免费搜索
"""

from __future__ import annotations

import json
import os
import re
from html.parser import HTMLParser
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

# 不输出文本内容的标签（脚本 / 样式 / 元数据）
_SKIP_TAGS = frozenset(
    {"script", "style", "noscript", "template", "head", "meta", "link"}
)
# 块级标签：闭合时补换行
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "header",
        "footer",
        "main",
        "aside",
        "ul",
        "ol",
        "table",
        "tr",
        "blockquote",
        "pre",
    }
)


class _TextExtractor(HTMLParser):
    """基于 html.parser 的纯文本提取器。

    使用真正的 HTML 解析器替代正则，避免 ``bad HTML filtering regexp``：
    - 自动处理畸形标签、嵌套、注释、CDATA；
    - 自动解码 HTML 实体（不再需要 ``html.unescape``）；
    - 通过 ``_skip_depth`` 计数正确剥离 ``<script>``/``<style>`` 等内嵌内容。
    """

    def __init__(self) -> None:
        # convert_charrefs=True：自动把 &amp; / &#x2F; 等还原为字符
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0  # 进入 script/style 等标签后 +1，离开 -1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "br":
            self._parts.append("\n")
        elif tag in _BLOCK_TAGS or tag in ("h1", "h2", "h3", "h4", "h5", "h6", "li"):
            # 块级元素前补一个换行，避免相邻块级文字粘连
            if self._parts and not self._parts[-1].endswith("\n"):
                self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if tag in _BLOCK_TAGS or tag in ("h1", "h2", "h3", "h4", "h5", "h6", "li"):
            self._parts.append("\n")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, Optional[str]]]
    ) -> None:
        if tag == "br":
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


class _MarkdownExtractor(HTMLParser):
    """基于 html.parser 的 Markdown 提取器。

    支持的转换：
    - <a href=...>text</a>  → [text](href)
    - <h1>..</h1> ~ <h6>..</h6> → # .. ###### ..
    - <li>..</li>           → - ..
    - <p>/<div>/<section>/<article> 块级元素 → 段落分隔
    - <br>/<hr>             → 换行
    其余标签会被剥离，文本内容保留。
    """

    _HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
    _PARAGRAPH_TAGS = frozenset({"p", "div", "section", "article"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        # 标签栈：用于在 endtag 时知道当前是不是 a / h*
        self._stack: list[dict[str, Any]] = []

    # ── 工具：当前是否在 skip 区或在收集子文本（如 <a> 内部）──
    def _in_collect(self) -> bool:
        return any(item.get("collect") for item in self._stack)

    def _append_text(self, text: str) -> None:
        if not text:
            return
        if self._stack and self._stack[-1].get("collect") is not None:
            # 收集到栈顶 entry 里
            self._stack[-1]["collect"].append(text)
        else:
            self._parts.append(text)

    # ── HTMLParser 钩子 ──
    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return

        attrs_dict = {k: v for k, v in attrs if v is not None}

        if tag == "a":
            self._stack.append(
                {"tag": "a", "href": attrs_dict.get("href", ""), "collect": []}
            )
            return
        if tag in self._HEADING_TAGS:
            self._parts.append("\n")
            self._stack.append({"tag": tag, "level": int(tag[1]), "collect": []})
            self._parts.append("#" * int(tag[1]) + " ")
            return
        if tag == "li":
            self._parts.append("\n- ")
            self._stack.append({"tag": "li"})
            return
        if tag == "br":
            self._append_text("\n")
            return
        if tag == "hr":
            self._parts.append("\n")
            return
        if tag in self._PARAGRAPH_TAGS:
            self._parts.append("\n\n")
            self._stack.append({"tag": tag})
            return

        # 其他标签仅入栈占位，不输出
        self._stack.append({"tag": tag})

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return

        # 弹出最近的同名标签（容错：若不匹配则忽略）
        idx = None
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i].get("tag") == tag:
                idx = i
                break
        if idx is None:
            return
        entry = self._stack.pop(idx)

        if tag == "a":
            inner = "".join(entry.get("collect") or []).strip()
            href = entry.get("href", "")
            if href and inner:
                self._parts.append(f"[{inner}]({href})")
            else:
                self._parts.append(inner)
            return
        if tag in self._HEADING_TAGS:
            inner = "".join(entry.get("collect") or []).strip()
            self._parts.append(inner + "\n")
            return
        if tag == "li":
            self._parts.append("\n")
            return
        if tag in self._PARAGRAPH_TAGS:
            self._parts.append("\n\n")
            return

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, Optional[str]]]
    ) -> None:
        if tag == "br":
            self._append_text("\n")
        elif tag == "hr":
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0 or not data:
            return
        self._append_text(data)

    def get_markdown(self) -> str:
        return "".join(self._parts)


def _strip_tags(text: str) -> str:
    """移除 HTML 标签并解码实体（基于 ``html.parser``，安全）。"""
    parser = _TextExtractor()
    try:
        parser.feed(text)
        parser.close()
    except Exception:  # pylint: disable=broad-except
        # 解析器对极端畸形输入兜底：返回已收集的部分
        pass
    return parser.get_text().strip()


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
    """将 HTML 转换为 Markdown 格式文本（基于 ``html.parser``，安全）。"""
    parser = _MarkdownExtractor()
    try:
        parser.feed(raw_html)
        parser.close()
    except Exception:  # pylint: disable=broad-except
        pass
    return _normalize(parser.get_markdown())


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
        url: str = "",
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
        query: str = "",
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

    def run(self, query: str = "", max_results: int = 3, **kwargs: Any) -> str:
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
