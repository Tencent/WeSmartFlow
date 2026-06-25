"""子 Agent 工厂：planner / researcher / tex_writer / exercises 与图像工具。"""

from __future__ import annotations

import logging
import os
from typing import Dict

from agent_core.agent import ReActAgent
from agent_core.context.profile_skill import ContextBuilderWithProfileAndSkill
from agent_core.context.simple import SimpleContextBuilder
from agent_core.layout import UserDataLayout
from agent_core.tool import (
    ArxivSearch,
    LatexPdfCompileTool,
    ReadFileTool,
    TavilySearch,
    ToolRegistry,
    WebFetch,
    WriteFileTool,
)
from agents.tools.image_gen_factory import build_image_gen_tool
from config import TEX_TEMPLATE_DIR

logger = logging.getLogger(__name__)


def build_sub_agents(layout: UserDataLayout, user_id) -> Dict[str, ReActAgent]:
    """构建 4 个独立子 Agent。"""
    from database import get_setting
    from services.llm_factory import get_llm

    tavily_key = get_setting(user_id, "tavily_api_key") or os.getenv(
        "TAVILY_API_KEY", ""
    )

    # 沉浸式学习不走"免费 100 次"额度限制：LLM / 搜索 / 图像 hook 均置空
    _search_hook = None
    _image_hook = None

    planner = ReActAgent(
        llm=get_llm(user_id),
        context_builder=ContextBuilderWithProfileAndSkill(
            workspace_dir=layout.root,
            user_id=user_id,
            base_prompt=(
                "你是一个专业的课程规划师。根据用户的学习主题，"
                "规划一份循序渐进的课程大纲。\n\n"
                "**工作流程**：\n"
                "1. 可选：使用搜索工具了解该主题的主流学习路线\n"
                "2. 设计 3-6 章课程大纲\n"
                "3. 使用 write_file 将大纲写入指定的 outline.json 路径\n"
                "4. 返回大纲的文本摘要\n\n"
                "**outline.json 格式**：\n"
                '{"topic": "主题", "overview": "介绍",\n'
                ' "chapters": [{"chapter_id": 1, "title": "标题",\n'
                '   "description": "目标", "knowledge_points": ["知识点"],\n'
                '   "estimated_hours": 1, "difficulty": "基础",\n'
                '   "search_keywords": ["关键词"]}]}\n\n'
                "要求：循序渐进，每章 3-6 个知识点，标注难度。"
            ),
        ),
        tool_registry=ToolRegistry(
            [
                TavilySearch(api_key=tavily_key, before_call_hook=_search_hook),
                ArxivSearch(),
                WebFetch(),
                WriteFileTool(),
            ]
        ),
        max_steps=10,
    )

    researcher = ReActAgent(
        llm=get_llm(user_id),
        context_builder=SimpleContextBuilder(
            "你是信息检索与整理助手。根据章节信息检索资料，整理为 JSON 写入指定路径。\n\n"
            "**JSON 输出格式**：\n"
            '{"chapter_id": N, "chapter_title": "...",\n'
            '  "sources": [{"title": "标题", "url": "https://...", "summary": "一句话摘要"}],\n'
            '  "raw_text": "整合后的 Markdown 正文（不超过 2000 字）"}\n\n'
            "**raw_text 必须遵守的格式规范**（前端会以 Markdown 直接渲染，质量直接影响用户体验）：\n"
            "1. 必须使用 Markdown 结构：用 `### 小节标题` 分块，每块下用短段落 + 列表，避免出现整段大段文字。\n"
            "2. 严禁出现裸 URL；若需引用网址，**必须**写成 `[显示文本](https://...)` 的 markdown 链接形式。\n"
            "3. 数学公式使用 LaTeX：行内用 `$...$`，独立公式用 `$$...$$`。\n"
            "4. 重要术语和关键概念用 `**加粗**`，对易混淆点可用 `> 引用块` 提醒。\n"
            "5. 不要把 sources 里的链接列表再原样附在 raw_text 末尾（前端会单独展示）。\n"
            "6. 内容要求循序渐进：先给定义/直观解释，再给关键性质/算法步骤，最后给注意事项或常见误区。\n"
            "7. 优先使用中文资料；如果只有英文，请翻译为中文表达。\n\n"
            "**工作流程**：\n"
            "1. 用 search 工具检索 2-4 条权威资料\n"
            "2. （可选）对最相关的 1-2 条用 web_fetch 抓取详细内容\n"
            "3. 整合为符合上述规范的 raw_text，并将 sources 列表填好\n"
            "4. 用 write_file 写入指定的 research.json 路径"
        ),
        tool_registry=ToolRegistry(
            [
                TavilySearch(api_key=tavily_key, before_call_hook=_search_hook),
                ArxivSearch(),
                WebFetch(),
                WriteFileTool(),
            ]
        ),
        max_steps=8,
    )

    tex_writer = ReActAgent(
        llm=get_llm(user_id),
        context_builder=ContextBuilderWithProfileAndSkill(
            workspace_dir=layout.root,
            user_id=user_id,
            base_prompt=(
                "你是 LaTeX Beamer 讲义设计师。根据章节信息，从文件系统读取参考资料，生成教学插图，撰写 TeX 源码，编译为 PDF。\n"
                "严格遵循 tex_beamer_writing 技能中的所有格式规范和文件系统协议。"
            ),
        ),
        tool_registry=ToolRegistry(
            [
                ReadFileTool(),
                WriteFileTool(),
                build_image_gen_tool(user_id, before_call_hook=_image_hook),
                LatexPdfCompileTool(TEX_TEMPLATE_DIR),
            ]
        ),
        max_steps=15,
    )

    exercises = ReActAgent(
        llm=get_llm(user_id),
        context_builder=ContextBuilderWithProfileAndSkill(
            workspace_dir=layout.root,
            user_id=user_id,
            base_prompt=(
                "你是教育习题设计师。读取 TeX 讲义，生成**恰好 9 道单选题**写入 .md 文件。\n"
                "题目必须按难度分为 3 组：3 道简单 + 3 道中等 + 3 道困难，且按此顺序排列。\n"
                "每题 4 个选项 A/B/C/D，必须有正确答案与解析。\n\n"
                "**严格输出格式**（整个文件必须完全遵循，不要添加任何额外内容）：\n"
                "```\n"
                "### 第1题 [简单]\n"
                "**题干：** 这里写题目内容\n\n"
                "A. 选项A内容\n"
                "B. 选项B内容\n"
                "C. 选项C内容\n"
                "D. 选项D内容\n\n"
                "**答案：** A\n"
                "**解析：** 这里写解析内容（一段话即可，不要分行列表）\n\n"
                "### 第2题 [简单]\n"
                "...（重复上述结构）\n"
                "```\n\n"
                "**强制要求**：\n"
                "- 必须恰好 9 道题，标题严格按 `### 第N题 [难度]` 格式，N 从 1 到 9\n"
                "- 难度标签必须是中括号包裹的 `[简单]` / `[中等]` / `[困难]` 三选一\n"
                "- 第 1-3 题为 [简单]，第 4-6 题为 [中等]，第 7-9 题为 [困难]\n"
                "- 题干、答案、解析行必须以 `**xxx：**` 加粗冒号开头\n"
                "- 不要使用 <details>、<summary>、HTML 标签\n"
                "- 不要生成填空题/简答题/判断题，只能是 4 选 1 的单选\n"
                "- 答案行只写字母 A / B / C / D，不要写成 'A. xxx'\n"
                "- 解析必须是连续文本，不要列表/分点，确保前端单行渲染美观"
            ),
        ),
        tool_registry=ToolRegistry([ReadFileTool(), WriteFileTool()]),
        max_steps=8,
    )

    return {
        "planner": planner,
        "researcher": researcher,
        "tex_writer": tex_writer,
        "exercises": exercises,
    }
