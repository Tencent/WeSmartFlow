"""
GenerateHtmlCardTool：委派 HtmlCardWriterAgent（subagent）生成 HTML 知识卡片

Tutor Agent 只需描述"想展示什么内容"，HtmlCardWriterAgent 负责：
  1. 如需插图，调用 generate_teaching_image 生成图片到工作目录
  2. 直接输出完整的 HTML body 片段（含 <img> 引用）

生成的 HTML 保存至 documents/cards/{card_id}/card.html，成功时返回 JSON。
"""

from __future__ import annotations

import html
import json
import logging
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from agent_core.agent.events import AgentFinalEvent
from agent_core.agent.react import ReActAgent
from agent_core.context.simple import SimpleContextBuilder
from agent_core.tool.base import BaseTool
from agent_core.tool.registry import ToolRegistry
from config import CARDS_DIR
from services.llm_factory import get_llm
from services.quota import check_and_consume
from repositories.document_repo import DocumentRepository


logger = logging.getLogger(__name__)

# ── CSS 样式（与 test_html_gen.py 保持同步） ──────────────────────────────────
_CSS = """<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;
    background: #fff;
    margin: 0;
    padding: 0;
    color: #1a1a1a;
    line-height: 1.6;
    font-size: 14px;
  }
  .card {
    background: #fff;
    border-radius: 0;
    padding: 24px 28px;
    border: none;
    position: relative;
    overflow: hidden;
    max-width: 100%;
  }  .card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #4f46e5 0%, #7c3aed 40%, #0ea5e9 100%);
  }
  .card-title { font-size: 22px; font-weight: 700; color: #111; line-height: 1.3; margin-bottom: 4px; }
  .card-title::after { content: ''; display: block; width: 36px; height: 3px; background: #4f46e5; margin-top: 8px; border-radius: 2px; }
  .card-subtitle { font-size: 13px; font-weight: 600; color: #4f46e5; text-transform: uppercase; letter-spacing: 0.06em; margin: 20px 0 8px; }
  .card-body { font-size: 14px; color: #444; margin-bottom: 10px; line-height: 1.65; }
  .highlight-box { border-left: 4px solid; border-image: linear-gradient(to bottom, #4f46e5, #7c3aed) 1; background: #f8f8ff; padding: 10px 14px; margin: 10px 0; font-size: 14px; color: #333; line-height: 1.6; }
  .highlight-box strong { color: #111; }
  .formula-center { background: linear-gradient(135deg, #f0f0ff 0%, #e8f0ff 100%); border: 1.5px solid #c7d2fe; border-radius: 8px; padding: 10px 20px; margin: 8px 0; text-align: center; font-size: 16px; color: #3730a3; overflow-x: auto; box-shadow: 0 2px 8px rgba(79,70,229,0.08); }
  .formula-block { background: #f0f4ff; color: #1e293b; border: 1.5px solid #c7d2fe; border-radius: 8px; padding: 10px 16px; margin: 8px 0; overflow-x: auto; line-height: 1.8; font-size: 14px; }
  .formula-block .katex { color: #3730a3; }
  .stat-row { display: flex; gap: 10px; margin: 12px 0; flex-wrap: wrap; }
  .stat-card { flex: 1; min-width: 80px; background: #f8f7ff; border: 1px solid #e0e7ff; border-radius: 8px; padding: 14px 12px; text-align: center; }
  .stat-card .num { font-size: 22px; font-weight: 800; color: #4f46e5; line-height: 1.2; font-family: 'JetBrains Mono', 'Fira Code', monospace; }
  .stat-card .label { font-size: 11px; color: #6b7280; margin-top: 4px; line-height: 1.4; }
  .flow-row { display: flex; align-items: stretch; gap: 0; margin: 14px 0; width: 100%; }
  .flow-node { flex: 1; display: flex; align-items: center; justify-content: center; text-align: center; padding: 10px 8px; font-size: 13px; font-weight: 600; color: #fff; line-height: 1.3; background: #4f46e5; }
  .flow-row .flow-node:nth-child(1) { background: #4f46e5; border-radius: 8px 0 0 8px; }
  .flow-row .flow-node:nth-child(3) { background: #7c3aed; }
  .flow-row .flow-node:nth-child(5) { background: #0ea5e9; }
  .flow-row .flow-node:nth-child(7) { background: #10b981; }
  .flow-row .flow-node:nth-child(9) { background: #f59e0b; }
  .flow-row .flow-node:last-child { border-radius: 0 8px 8px 0; }
  .flow-arrow { display: flex; align-items: center; justify-content: center; width: 0; flex-shrink: 0; align-self: stretch; position: relative; z-index: 1; }
  .flow-arrow::after { content: ''; display: block; width: 0; height: 0; border-top: 18px solid transparent; border-bottom: 18px solid transparent; border-left: 14px solid #e5e7eb; }
  .flow-row .flow-arrow:nth-child(2)::after { border-left-color: #4f46e5; }
  .flow-row .flow-arrow:nth-child(4)::after { border-left-color: #7c3aed; }
  .flow-row .flow-arrow:nth-child(6)::after { border-left-color: #0ea5e9; }
  .flow-row .flow-arrow:nth-child(8)::after { border-left-color: #10b981; }
  .compare-table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 13px; }
  .compare-table th { background: #4f46e5; color: #fff; padding: 8px 12px; text-align: left; font-weight: 600; font-size: 12px; }
  .compare-table td { padding: 8px 12px; border-bottom: 1px solid #f0f0f0; color: #444; vertical-align: top; }
  .compare-table tr:nth-child(even) td { background: #fafafa; }
  .compare-table tr:last-child td { border-bottom: none; }
  .progress-bar-wrap { display: flex; align-items: center; gap: 10px; margin: 6px 0; }
  .progress-label { font-size: 12px; color: #555; min-width: 90px; flex-shrink: 0; }
  .progress-bar { flex: 1; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; position: relative; }
  .progress-bar::after { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: var(--pct, 50%); background: #4f46e5; border-radius: 4px; }
  .progress-val { font-size: 12px; font-weight: 600; color: #4f46e5; min-width: 36px; text-align: right; flex-shrink: 0; }
  .tag { display: inline-block; background: #ede9fe; color: #5b21b6; border-radius: 3px; padding: 1px 8px; font-size: 12px; font-weight: 500; margin: 2px 3px 2px 0; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0; }
  .col-item { background: #fafafa; border: 1px solid #e8e8e8; border-radius: 6px; padding: 12px 14px; font-size: 14px; color: #444; line-height: 1.6; }
  .col-item strong { display: block; color: #111; font-size: 13px; margin-bottom: 4px; }
  .step-list { list-style: none; margin: 8px 0; counter-reset: step-counter; }
  .step-item { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 8px; font-size: 14px; color: #444; counter-increment: step-counter; }
  .step-item::before { content: counter(step-counter); background: #4f46e5; color: #fff; border-radius: 50%; min-width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; flex-shrink: 0; margin-top: 1px; }
  .divider { border: none; border-top: 1px solid #ebebeb; margin: 18px 0; }
  /* 插图：按原始比例自适应卡片宽度，禁止裁剪或拉伸 */
  .card-image { width: 100%; max-width: 100%; height: auto; border-radius: 8px; margin: 12px auto; display: block; object-fit: contain; object-position: center center; }
  .card-image-caption { font-size: 12px; color: #9ca3af; text-align: center; margin-top: -6px; margin-bottom: 10px; }
</style>"""

_KATEX_HEAD = """  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.css">
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/contrib/auto-render.min.js"
    onload="renderMathInElement(document.body, {
      delimiters: [
        {left: '$$', right: '$$', display: true},
        {left: '\\\\[', right: '\\\\]', display: true},
        {left: '\\\\(', right: '\\\\)', display: false},
        {left: '$', right: '$', display: false}
      ],
      throwOnError: false
    });"></script>"""

# ── HtmlCardWriterAgent 的 system prompt ──────────────────────────────────────
_HTML_CARD_WRITER_SYSTEM_PROMPT = """你是一个教育内容排版专家，专注生成精炼的 HTML 知识卡片。

## 工作流程

1. 根据用户提供的内容要求，设计一张知识卡片
2. 如果插图能明显提升理解（结构、场景、类比、地图、物体、人物/历史、流程直觉、空间关系、文化/生活化主题等），更积极地调用 generate_teaching_image 生成图片
   - output_dir 设为用户指定的工作目录
   - size 推荐 800x400（横图，适合卡片宽度）
   - 生成成功后，用 <img class="card-image" src="图片绝对路径"> 嵌入卡片
   - 不必等到用户明确要求图片；只要图片比纯 CSS 更直观，就可以生成
3. 直接输出 HTML body 片段（<body> 内部内容，不含 <!DOCTYPE>/<html>/<head>/<style>）

## 输出规则

1. 只输出 HTML 片段，不要任何 markdown 代码块包裹（不要 ```html）
2. 使用以下预定义 class（不要写内联 style）：

   【文字类】
   - .card-title        → 卡片大标题（必须有且只有一个）
   - .card-subtitle     → 副标题/章节标题
   - .card-body         → 正文段落（每段不超过 2 句话）
   - .highlight-box     → 高亮重点框
   - .tag               → 小标签（关键词）
   - .divider           → 分隔线

   【公式类】
   - .formula-center    → 居中核心公式（用 $$ 包裹 KaTeX 语法）
   - .formula-block     → 多行公式/代码块（深色背景）

   【图形/数据类】
   - .stat-row / .stat-card → 数值卡片行
   - .flow-row / .flow-node / .flow-arrow → 横向流程图
   - .compare-table     → 对比表格
   - .progress-bar-wrap / .progress-bar / .progress-label / .progress-val → 进度条

   【布局类】
   - .two-col / .col-item → 两列布局
   - .step-list / .step-item → 步骤列表

   【插图类】
   - .card-image        → 插图（<img> 标签，src 为 generate_teaching_image 返回的文件路径）。图片会按原始比例自适应卡片宽度，禁止设置固定 height、禁止 object-fit: cover，避免截断或拉伸失真。
   - .card-image-caption → 图片说明文字

3. 视觉优先：能用图形组件表达的内容，不要用纯文字描述
4. 数学公式用 KaTeX 语法：行内 $公式$，独立展示 $$公式$$
5. 禁止使用任何 emoji 或特殊符号图标
6. 禁止使用 Unicode 数学符号（∂ ∇ ·），必须用 LaTeX 命令（\\partial \\nabla \\cdot）
7. 禁止写内联 color/background 样式；必须使用预定义 class，避免文字和背景同色或对比度不足。

## 高速模板库（优先复用，减少生成耗时）

不要从零设计复杂布局。先判断内容类型，然后套用下列模板之一；只替换文字和少量结构：

1. 概念速览模板：
   <h1 class="card-title">标题</h1>
   <div class="highlight-box"><strong>一句话定义：</strong>...</div>
   <p class="card-body">核心解释...</p>
   <div class="tag">关键词</div>

2. 流程步骤模板：
   <h1 class="card-title">标题</h1>
   <div class="flow-row"><div class="flow-node">步骤1</div><div class="flow-arrow"></div><div class="flow-node">步骤2</div><div class="flow-arrow"></div><div class="flow-node">步骤3</div></div>
   <div class="highlight-box"><strong>关键点：</strong>...</div>

3. 对比表模板：
   <h1 class="card-title">标题</h1>
   <table class="compare-table"><tr><th>维度</th><th>A</th><th>B</th></tr><tr><td>...</td><td>...</td><td>...</td></tr></table>
   <p class="card-body">如何选择...</p>

4. 公式解释模板：
   <h1 class="card-title">标题</h1>
   <div class="formula-center">$$公式$$</div>
   <div class="two-col"><div class="col-item"><strong>符号含义</strong>...</div><div class="col-item"><strong>直观解释</strong>...</div></div>

5. 图文说明模板：
   <h1 class="card-title">标题</h1>
   <img class="card-image" src="图片路径">
   <div class="card-image-caption">图片说明</div>
   <div class="highlight-box"><strong>看图要点：</strong>...</div>

速度与效果平衡：公式、表格、流程、对比可优先用 HTML 组件表达；但当主题具有空间结构、真实场景、生活化案例、文化/历史背景、复杂物体或抽象概念需要类比时，应主动调用 generate_teaching_image。一般 3-5 张首轮卡片中建议至少 1 张使用真实插图；视觉主题可使用 2 张。

## 内容量控制（重要）

每张卡片必须严格控制内容量，确保在标准屏幕上不需要滚动即可完整显示：

- .card-subtitle 最多 **3 个**
- .card-body 每段最多 **2 句话**，全卡最多 **3 段**
- .highlight-box 最多 **2 个**
- .formula-center / .formula-block 最多 **3 个**
- .flow-row 节点数最多 **5 个**
- .compare-table 行数最多 **5 行**（含表头）
- .step-list 步骤最多 **5 步**
- .stat-row 数值卡片最多 **4 个**
- .two-col 最多 **4 个 .col-item**
- 如有插图（.card-image），文字适当精简但不必减半，保留必要解释
- 整张卡片的 HTML 行数不超过 **80 行**

## Critique → Generate 质量循环（必须静默执行一次）

最终输出前，先在心里按以下标准批判当前草稿，并只输出修正后的 HTML：

1. 信息密度：
   - 过空：只有标题/一两句话/大面积留白 → 补一个关键图形组件或 highlight-box。
   - 过密：长段落、组件堆叠、表格过长 → 删减到 2-4 个核心信息块。
2. 结构清晰：必须有明确主标题；正文、重点、流程/对比/公式/插图之间层级清楚。
3. 展示合理：优先使用「标题 + 1 个视觉组件 + 1 个重点框/短解释」的稳定结构。
4. 视觉均衡：不要连续堆 3 个以上同类组件；不要只放纯文字；不要为了填满而添加无关内容。
5. 图片安全：图片必须使用 .card-image，保持原始比例自适应，不裁剪、不拉伸；如果图片能帮助用户建立直观印象，优先保留图片而不是替换成纯文字。
"""


def _build_html_card_writer_agent(work_dir: Path, user_id: str) -> ReActAgent:
    """创建 HtmlCardWriterAgent，工作目录限定在 work_dir 下，支持插图生成。"""

    def _image_hook():
        check_and_consume(user_id, "image")

    from agents.tools.image_gen_factory import build_image_gen_tool

    tools = ToolRegistry(
        [
            build_image_gen_tool(user_id, before_call_hook=_image_hook),
        ]
    )
    return ReActAgent(
        llm=get_llm(user_id),
        context_builder=SimpleContextBuilder(_HTML_CARD_WRITER_SYSTEM_PROMPT),
        tool_registry=tools,
        max_steps=7,
        llm_config={"temperature": 0.5},
    )


def _wrap_html(body_html: str, title: str) -> str:
    """将 body 片段包装成完整 HTML 页面。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  {_CSS}
  {_KATEX_HEAD}
</head>
<body>
  <div class="card">
    {body_html}
  </div>
</body>
</html>"""


def _clean_body_html(raw: str) -> str:
    """清理模型输出：去除 markdown 代码块包裹、emoji、多余空行。"""
    # 去除 ```html ... ``` 包裹
    raw = re.sub(r"^```(?:html)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw.strip())
    # 清除 emoji
    raw = re.sub(
        r"[\U00010000-\U0010ffff\U00002600-\U000027BF\U0001F300-\U0001F9FF]", "", raw
    )
    # 压缩空行
    raw = re.sub(r"\n\s*\n+", "\n", raw).strip()
    return raw


_TAG_RE = re.compile(
    r"<(?P<tag>[a-zA-Z][\w:-]*)(?P<attrs>[^>]*)>(?P<body>[\s\S]*?)</(?P=tag)>", re.I
)


def _plain_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _has_class(attrs: str, class_name: str) -> bool:
    match = re.search(r"class=[\"']([^\"']*)[\"']", attrs or "", re.I)
    return bool(match and class_name in match.group(1).split())


def _limit_class_blocks(body_html: str, class_name: str, limit: int) -> tuple[str, int]:
    """保留指定 class 的前 limit 个块，删除后续同类块，避免过密。"""
    seen = 0
    removed = 0

    def repl(match: re.Match) -> str:
        nonlocal seen, removed
        if not _has_class(match.group("attrs"), class_name):
            return match.group(0)
        seen += 1
        if seen <= limit:
            return match.group(0)
        removed += 1
        return ""

    return _TAG_RE.sub(repl, body_html), removed


def _truncate_class_text(
    body_html: str, class_name: str, max_chars: int
) -> tuple[str, int]:
    """截断指定 class 的纯文本内容，避免长段落撑爆卡片。"""
    changed = 0

    def repl(match: re.Match) -> str:
        nonlocal changed
        attrs = match.group("attrs")
        if not _has_class(attrs, class_name):
            return match.group(0)
        inner = match.group("body")
        if "<" in inner:
            return match.group(0)
        text = _plain_text(inner)
        if len(text) <= max_chars:
            return match.group(0)
        changed += 1
        short = html.escape(text[:max_chars].rstrip() + "…")
        return f"<{match.group('tag')}{attrs}>{short}</{match.group('tag')}>"

    return _TAG_RE.sub(repl, body_html), changed


_NAMED_COLORS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "transparent": None,
}


def _parse_color(value: str):
    """解析常见 CSS 颜色，无法解析时返回 None。"""
    if not value:
        return None
    value = value.strip().lower()
    if value in _NAMED_COLORS:
        return _NAMED_COLORS[value]
    if value.startswith("#"):
        hex_value = value[1:]
        if len(hex_value) == 3:
            hex_value = "".join(ch * 2 for ch in hex_value)
        if len(hex_value) == 6:
            try:
                return tuple(int(hex_value[i : i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                return None
    match = re.match(r"rgba?\(([^)]+)\)", value)
    if match:
        parts = [p.strip() for p in match.group(1).split(",")[:3]]
        try:
            return tuple(max(0, min(255, int(float(p)))) for p in parts)
        except ValueError:
            return None
    return None


def _luminance(rgb) -> float:
    def channel(v: int) -> float:
        c = v / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg, bg) -> float:
    l1, l2 = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def _repair_low_contrast_styles(body_html: str) -> tuple[str, bool]:
    """修复内联 style 中文字/背景同色或对比度不足的问题。"""
    changed = False

    def repl(match: re.Match) -> str:
        nonlocal changed
        quote = match.group(1)
        style = match.group(2)
        decls = []
        props: dict[str, str] = {}
        for raw in style.split(";"):
            if ":" not in raw:
                continue
            key, value = raw.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if not key or not value:
                continue
            props[key] = value
            decls.append((key, value))

        fg = _parse_color(props.get("color", ""))
        bg = _parse_color(props.get("background-color", "")) or _parse_color(
            props.get("background", "")
        )
        if fg is None and bg is None:
            return match.group(0)

        repaired = False
        if fg is not None and bg is not None and _contrast_ratio(fg, bg) < 4.5:
            props["color"] = "#fff" if _luminance(bg) < 0.45 else "#111"
            repaired = True
        elif fg is not None and _contrast_ratio(fg, (255, 255, 255)) < 4.5:
            props["color"] = "#111"
            repaired = True
        elif fg is None and bg is not None and _luminance(bg) < 0.45:
            props["color"] = "#fff"
            repaired = True

        if not repaired:
            return match.group(0)

        changed = True
        ordered_keys = []
        for key, _ in decls:
            if key not in ordered_keys:
                ordered_keys.append(key)
        if "color" not in ordered_keys:
            ordered_keys.append("color")
        new_style = "; ".join(
            f"{key}: {props[key]}" for key in ordered_keys if key in props
        )
        return f"style={quote}{new_style}{quote}"

    repaired_html = re.sub(r"style=([\"'])([^\"']*)\1", repl, body_html, flags=re.I)
    return repaired_html, changed


def _normalize_images(body_html: str) -> str:
    """统一图片标签，移除会导致裁剪/拉伸的样式和属性。"""

    def repl(match: re.Match) -> str:
        attrs = match.group(1)
        attrs = re.sub(r"\sheight=[\"'][^\"']*[\"']", "", attrs, flags=re.I)
        attrs = re.sub(r"\swidth=[\"'][^\"']*[\"']", "", attrs, flags=re.I)

        class_match = re.search(r"class=[\"']([^\"']*)[\"']", attrs, re.I)
        if class_match:
            classes = class_match.group(1).split()
            if "card-image" not in classes:
                classes.append("card-image")
            attrs = re.sub(
                r"class=[\"'][^\"']*[\"']",
                f'class="{" ".join(classes)}"',
                attrs,
                count=1,
                flags=re.I,
            )
        else:
            attrs += ' class="card-image"'

        style_match = re.search(r"style=[\"']([^\"']*)[\"']", attrs, re.I)
        if style_match:
            style = style_match.group(1)
            style = re.sub(
                r"(?:^|;)\s*(height|max-height|object-fit)\s*:[^;]*",
                "",
                style,
                flags=re.I,
            )
            style = style.strip("; ")
            if style:
                attrs = re.sub(
                    r"style=[\"'][^\"']*[\"']",
                    f'style="{style}"',
                    attrs,
                    count=1,
                    flags=re.I,
                )
            else:
                attrs = re.sub(
                    r"\sstyle=[\"'][^\"']*[\"']", "", attrs, count=1, flags=re.I
                )
        return f"<img{attrs}>"

    return re.sub(r"<img\b([^>]*)>", repl, body_html, flags=re.I)


def _assess_and_repair_card_html(
    body_html: str, *, title: str, content: str
) -> tuple[str, list[str]]:
    """轻量 critique→repair：不用额外 LLM，仅做确定性质量修复，保证速度。"""
    issues: list[str] = []
    body_html = _normalize_images(body_html)
    body_html, contrast_fixed = _repair_low_contrast_styles(body_html)
    if contrast_fixed:
        issues.append("修复低对比度样式")

    if "card-title" not in body_html:
        body_html = f'<h1 class="card-title">{html.escape(title)}</h1>\n' + body_html
        issues.append("补充标题")

    limits = {
        "card-subtitle": 3,
        "card-body": 3,
        "highlight-box": 2,
        "formula-center": 3,
        "formula-block": 3,
        "flow-row": 1,
        "compare-table": 1,
        "step-list": 1,
        "stat-row": 1,
        "two-col": 1,
    }
    for class_name, limit in limits.items():
        body_html, removed = _limit_class_blocks(body_html, class_name, limit)
        if removed:
            issues.append(f"删减过多 {class_name}")

    for class_name, max_chars in {
        "card-body": 120,
        "highlight-box": 150,
        "col-item": 120,
        "step-item": 90,
    }.items():
        body_html, changed = _truncate_class_text(body_html, class_name, max_chars)
        if changed:
            issues.append(f"压缩过长 {class_name}")

    plain = _plain_text(body_html)
    visual_blocks = sum(
        body_html.count(cls)
        for cls in (
            "highlight-box",
            "formula-center",
            "formula-block",
            "flow-row",
            "compare-table",
            "step-list",
            "stat-row",
            "two-col",
            "card-image",
        )
    )
    body_count = len(re.findall(r"class=[\"'][^\"']*card-body", body_html, re.I))

    if len(plain) < 120 or (visual_blocks == 0 and body_count <= 1):
        summary = _plain_text(content)[:110]
        if summary:
            body_html += (
                '\n<div class="highlight-box"><strong>核心提示：</strong>'
                f"{html.escape(summary)}"
                "</div>"
            )
            issues.append("补足过空内容")

    if len(plain) > 950:
        body_html, removed = _limit_class_blocks(body_html, "card-body", 2)
        if removed:
            issues.append("二次删减长正文")

    body_html = re.sub(r"\n\s*\n+", "\n", body_html).strip()
    return body_html, issues


class GenerateHtmlCardTool(BaseTool):
    """
    委派 HtmlCardWriterAgent 生成单张 HTML 知识卡片，支持插图。

    接口与 GenerateCardTool（PDF版）对齐：接收 title + content，
    返回 JSON {file_id, script}，其中 file_id 是 documents.id。
    """

    name = "generate_html_card"
    description = (
        "生成一张 HTML 知识卡片（支持公式渲染、流程图、对比表格、插图等）。"
        "每张卡片聚焦一个知识点，你提供标题和内容描述，排版由卡片生成器负责。"
        "同一次对话可以多次调用，为不同子概念各生成一张卡片。"
        "成功时返回 JSON：{file_id, script}，其中 script 是这张卡片的口语化讲解稿（100-200字）。"
        "失败时返回 Error: 开头的错误信息。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "卡片标题，简洁有力，如'Flow Matching — 核心思路'",
            },
            "content": {
                "type": "string",
                "description": (
                    "卡片需要展示的内容，自然语言描述，越详细越好。"
                    "包括：核心概念、关键要点、具体例子、公式、对比、流程步骤等。"
                    "如需插图，在描述中说明'需要一张XXX的示意图'。"
                ),
            },
            "node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "关联的知识节点ID列表（可选）",
            },
        },
        "required": ["title", "content"],
    }

    def __init__(self, user_id=None, session_id=None, on_result_hook=None):
        super().__init__(on_result_hook=on_result_hook)
        self.user_id = user_id
        self.session_id = session_id

    def run(self, **kwargs):
        raise NotImplementedError("GenerateHtmlCardTool 仅支持 async_stream_run 调用")

    async def async_stream_run(
        self,
        title: str,
        content: str,
        node_ids: list = None,
        **_,
    ):
        """流式版本：透传 HtmlCardWriterAgent 的所有流式事件，最后 yield 最终 JSON 字符串。

        Yields:
            AgentStreamEvent | str
        """
        card_id = str(uuid.uuid4())

        with tempfile.TemporaryDirectory(prefix=f"html_card_{card_id}_") as _tmp:
            work_dir = Path(_tmp)
            card_dir = CARDS_DIR / card_id
            card_dir.mkdir(parents=True, exist_ok=True)

            instruction = (
                f"请生成一张标题为「{title}」的 HTML 知识卡片。\n\n"
                f"内容要求：\n{content}\n\n"
                f"工作目录（图片输出目录）：{work_dir}\n\n"
                f"直接输出 HTML body 片段，不要任何 markdown 代码块包裹。"
            )

            agent = _build_html_card_writer_agent(
                work_dir, user_id=self.user_id or "default"
            )

            yield f"正在生成知识卡片「{title}」..."

            # 透传 HtmlCardWriterAgent 的所有流式事件
            body_html = ""
            try:
                async for event in agent.async_stream(instruction):
                    yield event
                    # 收集最终输出（AgentFinalEvent.content）
                    if isinstance(event, AgentFinalEvent):
                        body_html = event.content or ""
            except Exception as e:  # pylint: disable=broad-except
                logger.exception(
                    "[GenerateHtmlCardTool] HtmlCardWriterAgent 流式运行异常"
                )
                yield f"Error: 生成卡片失败 — {e}"
                return

            if not body_html or len(body_html) < 50:
                yield "Error: 卡片生成失败 — HTML 内容为空"
                return

            # 清理 body HTML，并做一次轻量 critique→repair（无额外 LLM 调用，尽量不影响速度）
            body_html = _clean_body_html(body_html)
            body_html, quality_issues = _assess_and_repair_card_html(
                body_html, title=title, content=content
            )
            if quality_issues:
                logger.info(
                    "HTML 卡片已自动做排版质量微调: %s", ", ".join(quality_issues)
                )
                yield "已完成卡片排版质量检查"

            # 移动图片到 card_dir/images/，并将 body_html 中的临时路径替换为 /asset/ URL
            img_extensions = {".png", ".jpg", ".jpeg", ".webp"}
            images_dir = card_dir / "images"
            for img_file in work_dir.iterdir():
                if img_file.suffix.lower() in img_extensions:
                    images_dir.mkdir(parents=True, exist_ok=True)
                    dest = images_dir / img_file.name
                    shutil.move(str(img_file), str(dest))
                    # 替换为 documents asset URL：/api/documents/{card_id}/asset/images/{filename}
                    url_path = f"/api/documents/{card_id}/asset/images/{img_file.name}"
                    # macOS 下 /tmp 是 /private/tmp 的符号链接，需同时替换两种路径形式
                    body_html = body_html.replace(str(img_file.resolve()), url_path)
                    body_html = body_html.replace(str(img_file), url_path)

            # 包装成完整 HTML
            full_html = _wrap_html(body_html, title)

            # 保存 HTML 文件
            html_path = card_dir / "card.html"
            html_path.write_text(full_html, encoding="utf-8")

            yield "卡片生成完成"

            script = ""

            # 创建文档记录
            self._create_document_record(card_id, "card.html", title, content, node_ids)

            # file_id 即 documents.id（与 card_id 一致）
            yield json.dumps(
                {"file_id": card_id, "script": script},
                ensure_ascii=False,
            )

    def _create_document_record(
        self,
        card_id: str,
        file_name: str,
        title: str,
        content_description: str,
        node_ids: list,
    ):
        """创建文档记录并建立与节点的关联。"""
        try:
            if not self.user_id:
                raise ValueError("GenerateHtmlCardTool 缺少 user_id，拒绝写入脏数据")

            html_path = CARDS_DIR / card_id / "card.html"
            DocumentRepository().register_produced(
                doc_id=card_id,
                user_id=self.user_id,
                title=title,
                file_path=html_path,
                file_type="html_card",
                session_id=self.session_id,
                generation_prompt=content_description,
                node_ids=node_ids or [],
            )
            logger.info("HTML 卡片文档记录创建成功: %s", card_id)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("创建 HTML 卡片文档记录失败: %s", e)
