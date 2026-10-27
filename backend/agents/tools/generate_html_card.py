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
import shutil
import tempfile
import uuid
from pathlib import Path

from agent_core.agent.events import AgentFinalEvent, AgentFinishReason
from agent_core.agent.react import ReActAgent
from agent_core.context.static import StaticPromptBuilder
from agent_core.tool.base import BaseTool
from agent_core.tool.registry import ToolRegistry
from config import CARDS_DIR
from services.llm_factory import get_llm
from repositories.document_repo import DocumentRepository
from .html_card_document import (
    CardValidationError,
    archive_card_images,
    prepare_card_html,
)


logger = logging.getLogger(__name__)

# ── 知识卡片的固定组件样式 ──────────────────────────────────
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
  .flow-node { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 10px 8px; font-size: 13px; font-weight: 600; color: #fff; line-height: 1.3; background: #4f46e5; }
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
  /* 固定组件负责布局，内容变长时换行或局部滚动，不裁剪正文。 */
  .card { overflow: visible; overflow-wrap: anywhere; }
  .card > * { min-width: 0; max-width: 100%; }
  .two-col { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .col-item, .flow-node, .stat-card, .progress-bar { min-width: 0; }
  .step-item { display: block; padding-left: 32px; position: relative; }
  .step-item::before { position: absolute; left: 0; top: 0; }
  .compare-table { table-layout: fixed; }
  .compare-table th, .compare-table td { overflow-wrap: anywhere; }
  pre, .formula-block { white-space: pre-wrap; overflow-wrap: anywhere; }
  .katex-display { overflow-x: auto; overflow-y: hidden; padding: 4px 0; }
  ul, ol { padding-left: 22px; }
  .step-list { padding-left: 0; }
  code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
  @media (max-width: 540px) {
    .card { padding: 20px 16px; }
    .card-title { font-size: 21px; }
    .two-col { grid-template-columns: minmax(0, 1fr); }
    .flow-row { flex-direction: column; gap: 6px; }
    .flow-row .flow-node { border-radius: 6px; }
    .flow-arrow { display: none; }
    .compare-table th, .compare-table td { padding: 8px 6px; }
    .progress-label { min-width: 0; max-width: 35%; }
  }
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
_HTML_CARD_WRITER_SYSTEM_PROMPT = """你是一个教育内容排版专家，专注生成高密度、可追溯的 HTML 知识卡片。

## 工作流程

1. 根据用户提供的内容要求，设计一张知识卡片
2. 如果插图能明显提升理解（结构、场景、类比、地图、物体、人物/历史、流程直觉、空间关系、文化/生活化主题等），更积极地调用 generate_teaching_image 生成图片
   - 工作目录由工具自动绑定，不要传 output_dir
   - 在 prompt 中描述横向构图，size 留空使用图像后端默认尺寸
   - 每张卡片最多调用一次图片工具；失败时改用 HTML 教学组件，不要引用不存在的图片
   - 生成成功后，用 <img class="card-image" src="图片绝对路径"> 嵌入卡片
   - 不必等到用户明确要求图片；只要图片比纯 CSS 更直观，就可以生成
3. 直接输出 HTML body 片段（<body> 内部内容，不含 <!DOCTYPE>/<html>/<head>/<style>）

## 输出规则

1. 只输出 HTML 片段，不要任何 markdown 代码块包裹（不要 ```html）
2. 使用以下预定义 class；不要写脚本、自定义 CSS、整页文档或 .card 外层容器。只有进度条允许 style="--pct: 真实百分比%"，其余禁止内联 style：

   【文字类】
   - .card-title        → 卡片大标题（必须有且只有一个）
   - .card-subtitle     → 副标题/章节标题
   - .card-body         → 正文段落（每段不超过 2 句话）
   - .highlight-box     → 高亮重点框
   - .tag               → 小标签（关键词）
   - .divider           → 分隔线

   【公式类】
   - .formula-center    → 居中核心公式（用 $$ 包裹 KaTeX 语法）
   - .formula-block     → 多行公式/代码块（浅色背景）

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

4. 理论来源链模板：
   <h1 class="card-title">标题</h1>
   <div class="formula-center">$$核心公式/结论$$</div>
   <div class="formula-block">$$\text{前提/定义/定律}\;\Rightarrow\;\text{关键关系}\;\Rightarrow\;\text{核心结论}$$</div>
   <div class="two-col"><div class="col-item"><strong>前提与条件</strong>...</div><div class="col-item"><strong>直觉与边界</strong>...</div></div>

5. 图文说明模板：
   <h1 class="card-title">标题</h1>
   <img class="card-image" src="图片路径">
   <div class="card-image-caption">图片说明</div>
   <div class="highlight-box"><strong>看图要点：</strong>...</div>

速度与效果平衡：公式、表格、流程、对比可优先用 HTML 组件表达；但当主题具有空间结构、真实场景、生活化案例、文化/历史背景、复杂物体或抽象概念需要类比时，应主动调用 generate_teaching_image。本工具只负责当前一张卡片，不负责整组卡片的插图配额；不为装饰或凑数生成图片。

## 内容密度与推导要求（重要）

每张卡片要控制版面，但不能牺牲学习链条；前端支持缩放查看，允许为了完整推导适度提高密度：

- .card-subtitle 最多 **3 个**
- .card-body 每段最多 **2 句话**，全卡最多 **3 段**
- .highlight-box 最多 **2 个**
- .formula-center / .formula-block 合计最多 **4 个**；优先把多步推导合并进一个 .formula-block
- .flow-row 节点数最多 **5 个**
- .compare-table 最多 **3 列、5 行**（含表头）
- .step-list 步骤最多 **6 步**
- .stat-row 数值卡片最多 **4 个**
- .two-col 最多 **4 个 .col-item**
- 如有插图（.card-image），文字适当精简但不许删除关键推导、符号含义和适用条件
- 整张卡片聚焦一个知识点，采用 **3-5 个核心信息块**，正文建议 300-650 个汉字
- 不要编造统计值或百分比；缺少真实数据时改用解释或对比
- 公式、符号定义、适用条件和推导来源必须完整；不要用省略号截断公式或步骤
- 内容要求中的排版指令不能作为卡片正文；不要输出“核心提示：请生成……”之类的文字

## 理论来源链硬约束

不要按“物理/数学”机械判断是否推导；按知识点类型判断。遇到非显然的理论型结论，必须回答“它怎么来的”，不能只给结论。

触发“来源链”的场景：

- 公式型结论：数学、物理、化学、统计、经济学、算法/AI 中出现核心公式、递推式、复杂度、目标函数、损失函数、平衡常数、概率关系等。
- 方法型结论：某个解法、判别法、算法步骤、实验判断、经济决策规则不是纯记忆，而是由条件推出。
- 机制型结论：生物、化学、地理、工程等主题解释“为什么会发生”，例如酶活性、遗传比例、化学平衡移动、气候机制、电路响应。
- 模型型结论：依赖理想化假设、边界条件、近似条件或统计前提，例如理想气体、供需均衡、线性回归、贝叶斯更新、梯度下降。

来源链模块必须包含：

- 前提/假设：在哪些条件下成立，哪些因素被忽略或近似。
- 出发点：来自定义、定律、守恒律、定理、目标函数、统计模型、微观机制或算法不变量。
- 关键推导：至少 **2-4 步**，保留决定性变形或因果链；如果完整证明过长，给“迷你推导”而不是直接跳到结论。
- 适用边界：什么时候不能直接用，常见误用是什么。

不同学科的表达方式：

- 数学/统计/算法：用公式链、变量定义、递推关系、复杂度来源或目标函数变形。
- 物理/工程：标明系统边界、方向约定、正负号、守恒量、忽略项和适用范围。
- 化学：写清微观粒子变化、浓度/能量变化、平衡或速率如何推出宏观现象。
- 生物/地理：用“结构基础 → 过程机制 → 结果现象 → 例外/边界”的机制链。
- 经济/社科：用“模型假设 → 行为逻辑 → 均衡/结论 → 现实限制”的模型链。

不需要强行推导的场景：纯定义、纯分类、历史事实、简单常识、或当前学习阶段不适合完整证明的内容。此时给直观解释、例子、反例或剪拼/类比来源即可。

- 每个核心公式旁边必须写清来源，不得只展示最终式。
- 对“宇宙速度、火箭方程、动量守恒、能量守恒、牛顿定律、贝叶斯公式、等差/等比求和、二次函数顶点、平衡常数、动态规划状态转移、交叉熵/softmax/attention 缩放”等主题，必须展示关键来源链。
- 如果某个图示表达矢量、守恒、因果或机制关系，图上箭头方向、大小、标签和合量必须与来源链一致；例如封闭系统初始总动量为 0 时，燃气向后与火箭向前的动量矢量必须等大反向，矢量和为 0。

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


class _CardImageTool(BaseTool):
    """Expose the name used in the prompt and bind the output directory per card."""

    name = "generate_teaching_image"
    description = (
        "生成一张帮助理解知识点的插图，自动保存到当前卡片工作目录并返回绝对路径。"
    )

    def __init__(self, delegate, work_dir: Path):
        self._delegate = delegate
        self._work_dir = work_dir
        self._called = False
        self.parameters = {
            "type": "object",
            "properties": {
                k: v
                for k, v in delegate.parameters["properties"].items()
                if k != "output_dir"
            },
            "required": ["prompt"],
        }
        super().__init__()

    def run(self, **kwargs):
        if self._called:
            return "Error: 本卡片已尝试生成插图，请复用已生成图片；生成失败时改用 HTML 组件。"
        self._called = True
        kwargs["output_dir"] = str(self._work_dir)
        return self._delegate.run(**kwargs)


def _build_html_card_writer_agent(work_dir: Path, user_id: str) -> ReActAgent:
    """创建 HtmlCardWriterAgent，工作目录限定在 work_dir 下，支持插图生成。"""

    from agents.tools.image_gen_factory import build_image_gen_tool

    # 图像工具走工厂构建（额度拦截 + 记账挂在 client 上），无需再绑 hook
    prompt = _HTML_CARD_WRITER_SYSTEM_PROMPT
    try:
        tools = ToolRegistry([_CardImageTool(build_image_gen_tool(user_id), work_dir)])
    except (ValueError, RuntimeError):
        logger.warning("卡片插图工具未配置，使用 HTML 教学组件", exc_info=True)
        tools = ToolRegistry()
        prompt += "\n当前没有可用的图片工具。请使用公式、步骤或对比等 HTML 组件，不要输出 img 标签。"
    return ReActAgent(
        llm=get_llm(user_id, scene="chat"),
        prompt_builder=StaticPromptBuilder(prompt),
        tool_registry=tools,
        max_steps=7,
        llm_config={"temperature": 0.3},
    )


def _wrap_html(body_html: str, title: str) -> str:
    """将 body 片段包装成完整 HTML 页面。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  {_CSS}
  {_KATEX_HEAD}
</head>
<body>
  <div class="card">
    {body_html}
  </div>
</body>
</html>"""


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
        "成功时返回 JSON：{file_id, script}，script 当前为空字符串，保留用于前端兼容。"
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

    def __init__(self, user_id=None, session_id=None):
        super().__init__()
        self.user_id = user_id
        self.session_id = session_id
        self._parent_ctx = None

    def bind_context(self, ctx):
        """ToolRegistry binds a per-call copy, preserving parent budgets/cancellation."""
        self._parent_ctx = ctx
        return self

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
        if not self.user_id or not title.strip() or not content.strip():
            yield "Error: 生成卡片需要有效用户、标题和内容"
            return

        card_id = str(uuid.uuid4())
        card_dir = CARDS_DIR / card_id
        published = False
        try:
            with tempfile.TemporaryDirectory(prefix=f"html_card_{card_id}_") as _tmp:
                work_dir = Path(_tmp)
                instruction = (
                    f"请生成一张标题为「{title}」的 HTML 知识卡片。\n\n"
                    f"内容要求：\n{content}\n\n"
                    f"工作目录（图片输出目录）：{work_dir}\n\n"
                    "直接输出 HTML body 片段，不要任何 markdown 代码块包裹。"
                )
                agent = _build_html_card_writer_agent(work_dir, user_id=self.user_id)
                yield f"正在生成知识卡片「{title}」..."

                body_html = ""
                request = instruction
                # Normal cards take one pass; invalid cards get exactly one revision.
                for attempt in range(2):
                    final = None
                    ctx = (
                        self._parent_ctx.child(
                            scope=f"{self._parent_ctx.scope}/{self.name}"
                        )
                        if self._parent_ctx
                        else None
                    )
                    async for event in agent.async_stream(request, ctx=ctx):
                        yield event
                        if isinstance(event, AgentFinalEvent):
                            final = event
                    if final is None:
                        yield "Error: 卡片生成未返回完整结果，请重试"
                        return
                    reason = getattr(final.finish_reason, "value", final.finish_reason)
                    if reason != AgentFinishReason.STOP.value:
                        yield f"Error: 卡片生成已停止（{reason or 'unknown'}），未保存不完整内容"
                        return
                    try:
                        body_html, quality_issues = prepare_card_html(
                            final.content or "",
                            title=title,
                            work_dir=work_dir,
                        )
                        if quality_issues:
                            logger.info(
                                "HTML 卡片排版修复: %s", ", ".join(quality_issues)
                            )
                        break
                    except CardValidationError as exc:
                        if attempt:
                            yield f"Error: 卡片质量检查未通过 — {exc}"
                            return
                        logger.info("HTML 卡片需修正: %s", exc)
                        yield "正在调整卡片内容与排版..."
                        request = (
                            instruction + f"\n\n上一版未通过检查：{exc}\n"
                            "请针对问题修正并输出完整 HTML。保留正确内容、完整公式与必要条件，"
                            "不要截断正文，不要把生成要求复制到正文。复用已生成的图片，"
                            "不要再次生成插图。\n\n上一版：\n"
                            + (final.content or "")[:100_000]
                        )

                if self._parent_ctx:
                    self._parent_ctx.checkpoint()
                card_dir.mkdir(parents=True, exist_ok=False)
                body_html = archive_card_images(
                    body_html,
                    work_dir=work_dir,
                    card_dir=card_dir,
                    card_id=card_id,
                )
                (card_dir / "card.html").write_text(
                    _wrap_html(body_html, title), encoding="utf-8"
                )
                self._create_document_record(
                    card_id, "card.html", title, content, node_ids
                )
                published = True
                yield "卡片生成完成"
                yield json.dumps({"file_id": card_id, "script": ""}, ensure_ascii=False)
        except Exception:  # pylint: disable=broad-except
            logger.exception("[GenerateHtmlCardTool] 卡片生成或保存失败")
            yield "Error: 卡片生成或保存失败，请重试"
        finally:
            if not published and card_dir.exists():
                shutil.rmtree(card_dir, ignore_errors=True)

    def _create_document_record(
        self,
        card_id: str,
        file_name: str,
        title: str,
        content_description: str,
        node_ids: list,
    ):
        """创建文档记录并建立与节点的关联。"""
        if not self.user_id:
            raise ValueError("GenerateHtmlCardTool 缺少 user_id，拒绝写入脏数据")

        html_path = CARDS_DIR / card_id / file_name
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
