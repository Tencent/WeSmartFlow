"""
GenerateHtmlCardTool：委派 HtmlCardWriterAgent（subagent）生成 HTML 知识卡片

Tutor Agent 只需描述"想展示什么内容"，HtmlCardWriterAgent 负责：
  1. 如需插图，调用 generate_teaching_image 生成图片到工作目录
  2. 直接输出完整的 HTML body 片段（含 <img> 引用）

生成的 HTML 保存至 documents/cards/{card_id}/card.html，成功时返回 JSON。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from agent_core.agent.base import AgentFinalEvent
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
  /* 插图 */
  .card-image { width: 100%; border-radius: 8px; margin: 12px 0; display: block; object-fit: cover; max-height: 320px; }
  .card-image-caption { font-size: 12px; color: #9ca3af; text-align: center; margin-top: -6px; margin-bottom: 10px; }
</style>"""

_KATEX_HEAD = """  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.css">
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/contrib/auto-render.min.js"
    onload="renderMathInElement(document.body, {
      delimiters: [
        {left: '$$', right: '$$', display: true},
        {left: '$', right: '$', display: false}
      ],
      throwOnError: false
    });"></script>"""

# ── HtmlCardWriterAgent 的 system prompt ──────────────────────────────────────
_HTML_CARD_WRITER_SYSTEM_PROMPT = """你是一个教育内容排版专家，专注生成精炼的 HTML 知识卡片。

## 工作流程

1. 根据用户提供的内容要求，设计一张知识卡片
2. 如需插图（用户明确要求或内容适合配图），先调用 generate_teaching_image 生成图片
   - output_dir 设为用户指定的工作目录
   - size 推荐 800x400（横图，适合卡片宽度）
   - 生成成功后，用 <img class="card-image" src="图片绝对路径"> 嵌入卡片
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
   - .card-image        → 插图（<img> 标签，src 为 generate_teaching_image 返回的文件路径）
   - .card-image-caption → 图片说明文字

3. 视觉优先：能用图形组件表达的内容，不要用纯文字描述
4. 数学公式用 KaTeX 语法：行内 $公式$，独立展示 $$公式$$
5. 禁止使用任何 emoji 或特殊符号图标
6. 禁止使用 Unicode 数学符号（∂ ∇ ·），必须用 LaTeX 命令（\\partial \\nabla \\cdot）

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
- 如有插图（.card-image），全卡文字内容减半
- 整张卡片的 HTML 行数不超过 **80 行**
"""


def _build_image_tool(user_id, before_call_hook=None):
    """构建图像生成工具实例。"""
    from agent_core.tool.openai_image_gen import OpenAIImageGenTool

    try:
        from database import get_setting

        api_key = get_setting(user_id, "img_api_key") or os.getenv("IMG_API_KEY", "any")
        base_url = get_setting(user_id, "img_base_url") or os.getenv(
            "IMG_BASE_URL", "http://localhost:8080/v1"
        )
        model = get_setting(user_id, "img_model") or os.getenv("IMG_MODEL") or None
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("图片生成配置读取失败（将使用默认值）: %s", e)
        api_key = os.getenv("IMG_API_KEY", "any")
        base_url = os.getenv("IMG_BASE_URL", "http://localhost:8080/v1")
        model = os.getenv("IMG_MODEL") or None

    return OpenAIImageGenTool(
        api_key=api_key,
        base_url=base_url,
        model=model,
        before_call_hook=before_call_hook,
    )


def _build_html_card_writer_agent(work_dir: Path, user_id: str) -> ReActAgent:
    """创建 HtmlCardWriterAgent，工作目录限定在 work_dir 下，支持插图生成。"""

    def _image_hook():
        check_and_consume(user_id, "image")

    tools = ToolRegistry(
        [
            _build_image_tool(user_id, before_call_hook=_image_hook),
        ]
    )
    return ReActAgent(
        llm=get_llm(user_id),
        context_builder=SimpleContextBuilder(_HTML_CARD_WRITER_SYSTEM_PROMPT),
        tool_registry=tools,
        max_steps=8,
        llm_config={"temperature": 0.6},
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


class GenerateHtmlCardTool(BaseTool):
    """
    委派 HtmlCardWriterAgent 生成单张 HTML 知识卡片，支持插图。

    接口与 GenerateCardTool（PDF版）对齐：接收 title + content，
    返回 JSON {file_id, script}，其中 file_id 指向 HTML 文件。
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

            # 清理 body HTML
            body_html = _clean_body_html(body_html)

            # 移动图片到 card_dir，并将 body_html 中的临时路径替换为可访问的 URL 路径
            img_extensions = {".png", ".jpg", ".jpeg", ".webp"}
            for img_file in work_dir.iterdir():
                if img_file.suffix.lower() in img_extensions:
                    dest = card_dir / img_file.name
                    shutil.move(str(img_file), str(dest))
                    # 替换为后端静态文件 URL（/files/cards/{card_id}/{filename}）
                    url_path = f"/files/cards/{card_id}/{img_file.name}"
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
            self._create_document_record(
                card_id, f"{card_id}/card.html", title, content, node_ids
            )

            yield json.dumps(
                {"file_id": f"{card_id}/card.html", "script": script},
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
            doc_repo = DocumentRepository()
            html_path = CARDS_DIR / card_id / "card.html"
            file_size = os.path.getsize(html_path) if html_path.exists() else 0
            storage_key = f"documents/cards/{card_id}/card.html"

            if not self.user_id:
                raise ValueError("GenerateHtmlCardTool 缺少 user_id，拒绝写入脏数据")

            doc_repo.create_generated(
                doc_id=card_id,
                user_id=self.user_id,
                title=title,
                file_name=file_name,
                storage_key=storage_key,
                file_type="html",
                file_size=file_size,
                generation_prompt=content_description,
                session_id=self.session_id,
                node_ids=node_ids or [],
            )
            logger.info("HTML 卡片文档记录创建成功: %s", card_id)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("创建 HTML 卡片文档记录失败: %s", e)
