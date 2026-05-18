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
    OpenAIImageGenTool,
    ReadFileTool,
    TavilySearch,
    ToolRegistry,
    WebFetch,
    WriteFileTool,
)
from config import TEX_TEMPLATE_DIR
from services.quota import check_and_consume

logger = logging.getLogger(__name__)


def build_image_tool(user_id, before_call_hook=None):
    """构建 OpenAI 兼容图像生成工具实例。"""
    try:
        from database import get_setting

        api_key = get_setting(user_id, "img_api_key") or os.getenv("IMG_API_KEY", "any")
        base_url = get_setting(user_id, "img_base_url") or os.getenv(
            "IMG_BASE_URL", "http://localhost:8080/v1"
        )
        model = get_setting(user_id, "img_model") or os.getenv("IMG_MODEL") or None
    except Exception as e:  # pylint: disable=broad-except
        logger.warning(
            "图片生成配置读取失败（将使用默认值，图片功能可能不可用）: %s", e
        )
        api_key = os.getenv("IMG_API_KEY", "any")
        base_url = os.getenv("IMG_BASE_URL", "http://localhost:8080/v1")
        model = os.getenv("IMG_MODEL") or None
    return OpenAIImageGenTool(
        api_key=api_key,
        base_url=base_url,
        model=model,
        before_call_hook=before_call_hook,
    )


def build_sub_agents(layout: UserDataLayout, user_id) -> Dict[str, ReActAgent]:
    """构建 4 个独立子 Agent。"""
    from database import get_setting
    from services.llm_factory import get_llm

    tavily_key = get_setting(user_id, "tavily_api_key") or os.getenv(
        "TAVILY_API_KEY", ""
    )

    # 搜索工具额度 hook
    def _search_hook():
        check_and_consume(user_id, "search")

    # 图像生成工具额度 hook
    def _image_hook():
        check_and_consume(user_id, "image")

    planner = ReActAgent(
        llm=get_llm(user_id),
        context_builder=ContextBuilderWithProfileAndSkill(
            workspace_dir=layout.root,
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
            "你是信息检索助手。根据章节信息搜索资料，整理为 JSON 写入指定路径。\n"
            'JSON 格式：{"chapter_id": N, "chapter_title": "...",\n'
            '  "sources": [{"title": "...", "url": "...", "summary": "..."}],\n'
            '  "raw_text": "整合后参考资料（2000字内）"}\n'
            "要求：优先中文资料，保留关键知识点和公式，标注来源 URL。"
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
            base_prompt=(
                "你是 LaTeX Beamer 讲义设计师。根据章节信息，从文件系统读取参考资料，生成教学插图，撰写 TeX 源码，编译为 PDF。\n"
                "严格遵循 tex_beamer_writing 技能中的所有格式规范和文件系统协议。"
            ),
        ),
        tool_registry=ToolRegistry(
            [
                ReadFileTool(),
                WriteFileTool(),
                build_image_tool(user_id, before_call_hook=_image_hook),
                LatexPdfCompileTool(TEX_TEMPLATE_DIR),
            ]
        ),
        max_steps=15,
    )

    exercises = ReActAgent(
        llm=get_llm(user_id),
        context_builder=ContextBuilderWithProfileAndSkill(
            workspace_dir=layout.root,
            base_prompt=(
                "你是教育习题设计师。读取 TeX 讲义，生成 8-12 道配套习题写入 .md 文件。\n"
                "题型多样（选择题、填空题、简答题），难度由易到难。\n"
                "每道题后附带答案和解析，用 <details> 标签折叠。"
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
