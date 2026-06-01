"""
GenerateCardTool：委派 CardWriterAgent（subagent）生成 PDF 知识卡片

Tutor Agent 只需描述"想展示什么内容"，CardWriterAgent 负责：
  1. 自主编写 Beamer .tex 源码
  2. 调用 latex_pdf_compile 编译 PDF
  3. 编译失败时自动修复重试

生成的 PDF 保存至 documents/cards/{card_id}/card.pdf，流式成功结果返回 JSON：{"file_id": "{card_id}/card.pdf", "script": "..."}。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from agent_core.agent.react import ReActAgent
from agent_core.context.simple import SimpleContextBuilder
from agent_core.tool.base import BaseTool
from agent_core.tool.filesystem import WriteFileTool
from agent_core.tool.openai_image_gen import OpenAIImageGenTool
from agent_core.tool.pdf_compile import LatexPdfCompileTool
from agent_core.tool.registry import ToolRegistry
from config import CARDS_DIR, TEX_TEMPLATE_DIR
from services.llm_factory import get_llm
from services.quota import check_and_consume
from repositories.document_repo import DocumentRepository


# CardWriterAgent 的 system prompt
_CARD_WRITER_SYSTEM_PROMPT = """你是精通 LaTeX Beamer 的卡片设计师，专注生成轻量、精炼的单页知识卡片。

## 工作流程

1. 根据用户提供的结构化内容，设计**恰好 1 页**的知识卡片
2. 如需插图，先调用 generate_teaching_image 生成图片到工作目录，再在 tex 中引用
3. 用 write_file 将完整 .tex 写入指定路径
4. 用 latex_pdf_compile 编译 PDF
5. 编译失败时根据错误日志修复后重试（最多 2 次）
6. 编译成功后简要说明已完成，无需输出文件路径

## 页数约束（最重要，硬性规则）

- **只生成 1 页内容页**，绝对不允许超过 1 页
- 每页不超过 6 行文字（含 itemize 条目），保持极度简洁
- **如果收到的内容超过一页能放下的量，必须主动裁剪，只保留最核心的 2-3 个要点**
- 宁可内容少，绝不多加一页
- 禁止使用 `\pause`、多个 `\begin{frame}` 或任何分页手段

## TeX 格式规范

必须遵守的文档结构：

\\documentclass[aspectratio=169,xcolor=dvipsnames]{beamer}
\\usetheme{SimplePlus}
\\usepackage{hyperref}
\\usepackage{graphicx}
\\usepackage{booktabs}
\\usepackage{amsmath,amssymb}
\\usepackage{xeCJK}

\\begin{document}

\\begin{frame}{要点}
  \\begin{itemize}
    \\item 要点一
  \\end{itemize}
\\end{frame}

\\end{document}

## 核心规则

1. 必须兼容 XeLaTeX，保留 \\usetheme{SimplePlus} + xeCJK
2. 自包含：不依赖外部 bib、minted、shell-escape、自定义 class
3. 优先使用 itemize/enumerate/columns/block/alertblock/exampleblock/table
4. 数学用标准 LaTeX 环境；禁止 Markdown 标题符号、代码围栏、HTML 标签
5. 不放练习题，不引用 .bib 文件
6. 插图用 \\includegraphics 引用实际生成的图片路径；图片生成失败则删除对应结构

## 宏包白名单

beamer, hyperref, graphicx, booktabs, amsmath, amssymb, xeCJK, tikz,
pgfplots, listings, xcolor, fontspec, unicode-math, multicol, multirow,
array, enumitem

禁用：minted、shell-escape、biblatex、natbib、fontenc

## 编译修复

- File 'xxx' not found → 删除对应 \\includegraphics 及其结构
- Missing } inserted → 补全括号
- Undefined control sequence → 检查拼写或删除该命令
- File 'xxx.sty' not found → 换用白名单内宏包
"""


def _build_image_tool(user_id, before_call_hook=None):
    """构建图像生成工具实例（OpenAI 兼容接口）。"""
    import logging
    import os

    _logger = logging.getLogger(__name__)

    try:
        from database import get_setting

        api_key = get_setting(user_id, "img_api_key") or os.getenv("IMG_API_KEY", "any")
        base_url = get_setting(user_id, "img_base_url") or os.getenv(
            "IMG_BASE_URL", "http://localhost:8080/v1"
        )
        model = get_setting(user_id, "img_model") or os.getenv("IMG_MODEL") or None
    except Exception as e:  # pylint: disable=broad-except
        _logger.warning(
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


def _build_card_writer_agent(work_dir: Path, user_id) -> ReActAgent:
    """创建 CardWriterAgent，工作目录限定在 work_dir 下，支持插图生成。"""

    def _image_hook():
        check_and_consume(user_id, "image")

    tools = ToolRegistry(
        [
            WriteFileTool(workspace=work_dir, allowed_dir=work_dir),
            _build_image_tool(user_id, before_call_hook=_image_hook),
            LatexPdfCompileTool(TEX_TEMPLATE_DIR),
        ]
    )
    return ReActAgent(
        llm=get_llm(user_id),
        context_builder=SimpleContextBuilder(_CARD_WRITER_SYSTEM_PROMPT),
        tool_registry=tools,
        max_steps=15,
        llm_config={"temperature": 0.3},
    )


class GenerateCardTool(BaseTool):
    """
    委派 CardWriterAgent 生成单页 PDF 知识卡片（Beamer + SimplePlus 主题）。

    Tutor Agent 描述想展示的内容，CardWriterAgent 负责编写 tex、编译 PDF。
    流式成功结果返回 JSON：{"file_id": "{card_id}/card.pdf", "script": "..."}；失败时返回 Error: 开头的错误信息。
    """

    name = "generate_card"
    description = (
        "生成一张单页 PDF 知识卡片（Beamer 风格，支持插图）。"
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
                "description": "卡片标题，简洁有力，如'快速排序 — 核心思路'",
            },
            "content": {
                "type": "string",
                "description": (
                    "卡片需要展示的内容，自然语言描述，越详细越好。"
                    "包括：核心概念、关键要点、具体例子、公式、对比、流程步骤等。"
                    "卡片生成器会据此自主设计排版，内容越丰富卡片质量越高。"
                ),
            },
            "node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "关联的知识节点ID列表，用于建立文档与节点的链接（可选）",
            },
        },
        "required": ["title", "content"],
    }

    def __init__(self, user_id=None, session_id=None, on_result_hook=None):
        super().__init__(on_result_hook=on_result_hook)
        self.user_id = user_id
        self.session_id = session_id

    def run(self, **kwargs):
        """占位实现（满足抽象基类要求）。实际调用路径为 async_stream_run。"""
        raise NotImplementedError("GenerateCardTool 仅支持 async_stream_run 调用")

    async def async_stream_run(
        self,
        title: str,
        content: str,
        node_ids: list = None,
        **_,
    ):
        """流式版本：透传 CardWriterAgent 的所有流式事件，最后 yield 最终 JSON 字符串。

        yield 顺序：
        1. CardWriterAgent.async_stream 产生的所有 AgentStreamEvent（透传给父 Agent）
        2. 最后 yield 一个 str（JSON 格式的 {file_id, script}），供父 Agent 写入 history

        Yields:
            AgentStreamEvent | str
        """
        logger = logging.getLogger(__name__)
        card_id = str(uuid.uuid4())

        with tempfile.TemporaryDirectory(prefix=f"card_{card_id}_") as _tmp:
            work_dir = Path(_tmp)
            tmp_tex = work_dir / "card.tex"
            tmp_pdf = work_dir / "card.pdf"
            card_dir = CARDS_DIR / card_id
            card_dir.mkdir(parents=True, exist_ok=True)

            instruction = (
                f"请生成一张标题为「{title}」的单页 PDF 知识卡片。\n\n"
                f"内容要求：\n{content}\n\n"
                f"【硬性约束】只生成 1 页，每页最多 6 行文字。"
                f"如果上面的内容超过一页能放下的量，请主动裁剪，只保留最核心的 2-3 个要点，宁少勿多。\n\n"
                f"工作目录：{work_dir}\n"
                f"tex 文件路径：{tmp_tex}\n"
                f"编译完成后 PDF 路径应为：{tmp_pdf}\n"
                f"如需插图，调用 generate_teaching_image 并将 output_dir 设为：{work_dir}\n\n"
                f"所有文件必须写在工作目录 {work_dir} 下，不得写到其他位置。"
            )

            agent = _build_card_writer_agent(
                work_dir, user_id=self.user_id or "default"
            )

            yield f"正在生成知识卡片「{title}」..."

            # 透传 CardWriterAgent 的所有流式事件
            try:
                async for event in agent.async_stream(instruction):
                    yield event
            except Exception as e:  # pylint: disable=broad-except
                logger.exception("[GenerateCardTool] CardWriterAgent 流式运行异常")
                yield f"Error: 生成卡片失败 — {e}"
                return

            # CardWriterAgent 完成后，处理产物
            if not tmp_pdf.exists():
                yield "Error: 卡片生成失败 — PDF 文件未生成"
                return

            yield "卡片编译完成，正在归档文件..."

            # 移动产物到最终目录
            final_tex = card_dir / "card.tex"
            final_pdf = card_dir / "card.pdf"
            if tmp_tex.exists():
                shutil.move(str(tmp_tex), str(final_tex))
            shutil.move(str(tmp_pdf), str(final_pdf))

            # 移动图片
            img_extensions = {".png", ".jpg", ".jpeg", ".webp"}
            for img_file in work_dir.iterdir():
                if img_file.suffix.lower() in img_extensions:
                    shutil.move(str(img_file), str(card_dir / img_file.name))

            # 资产归档
            try:
                from services.asset_service import archive_pdf, archive_image

                archive_pdf(
                    final_pdf,
                    title=title,
                    source_type="card",
                    session_id=self.session_id or "",
                )
                for img in card_dir.iterdir():
                    if img.suffix.lower() in img_extensions:
                        prompt = ""
                        meta_file = card_dir / f"{img.stem}.meta.json"
                        if meta_file.exists():
                            try:
                                prompt = json.loads(
                                    meta_file.read_text(encoding="utf-8")
                                ).get("prompt", "")
                            except Exception:  # pylint: disable=broad-except
                                pass
                        archive_image(
                            img, prompt=prompt, source_type="card", chapter=card_id
                        )
                logger.info("卡片 %s 资产归档完成", card_id)
            except Exception as arch_err:  # pylint: disable=broad-except
                logger.warning("卡片 %s 资产归档失败: %s", card_id, arch_err)

            yield "正在生成讲解稿..."

            # 生成讲解稿
            script = ""
            try:
                tex_content = (
                    final_tex.read_text(encoding="utf-8") if final_tex.exists() else ""
                )
                llm = get_llm(self.user_id)
                prompt = (
                    f"以下是一张标题为「{title}」的 LaTeX Beamer 知识卡片源码。\n"
                    f"请为这张卡片写一段口语化的讲解旁白，100-200字，"
                    f"用陈述句，语气自然，不要复读卡片文字，要有启发性。\n\n"
                    f"```tex\n{tex_content[:4000]}\n```\n\n"
                    f"只输出旁白文本，不要任何格式标记。"
                )
                response = await llm.async_think(
                    [{"role": "user", "content": prompt}],
                    config={"temperature": 0.6, "max_tokens": 400},
                )
                script = (response.content or "").strip()
            except Exception as e:  # pylint: disable=broad-except
                logger.warning("讲解稿生成失败: %s", e)

            if script:
                (card_dir / "script.txt").write_text(script, encoding="utf-8")

            yield "正在保存文档记录..."

            # 创建文档记录
            self._create_document_record(
                card_id, f"{card_id}/card.pdf", title, content, node_ids
            )

            # 最后 yield 最终结果字符串，供父 Agent 写入 history
            yield json.dumps(
                {"file_id": f"{card_id}/card.pdf", "script": script}, ensure_ascii=False
            )

    def _create_document_record(
        self,
        card_id: str,
        file_name: str,
        title: str,
        content_description: str,
        node_ids: list,
    ):
        """创建文档记录并建立与节点的关联"""
        try:
            doc_repo = DocumentRepository()

            card_dir = CARDS_DIR / card_id
            pdf_path = card_dir / "card.pdf"
            file_size = os.path.getsize(pdf_path) if pdf_path.exists() else 0
            storage_key = f"documents/cards/{card_id}/card.pdf"

            if not self.user_id:
                raise ValueError("GenerateCardTool 缺少 user_id，拒绝写入脏数据")
            doc = doc_repo.create_generated(
                doc_id=card_id,
                user_id=self.user_id,
                title=title,
                file_name=file_name,
                storage_key=storage_key,
                file_type="pdf",
                file_size=file_size,
                generation_prompt=content_description,
                session_id=self.session_id,
                node_ids=node_ids or [],
            )

            print(f"卡片文档记录创建成功: {doc.id}")

            # 回填 total_pages（从 tex 源码数 \begin{frame}）
            try:
                tex_path = card_dir / "card.tex"
                if tex_path.exists():
                    num_frames = tex_path.read_text(encoding="utf-8").count(
                        r"\begin{frame}"
                    )
                    if num_frames > 0:
                        doc_repo.set_pages(card_id, num_frames)
            except Exception as e:  # pylint: disable=broad-except
                print(f"回填卡片页数失败（忽略）: {e}")

        except Exception as e:  # pylint: disable=broad-except
            print(f"创建卡片文档记录失败: {e}")

    def _generate_card_audio(
        self, card_id: str, tex_path: Path, pdf_path: Path
    ) -> None:
        """为卡片生成 TTS 语音讲解（参考 immersive_service 的实现）。"""
        import json
        import re
        import logging
        from agent_core.tool.tts_say import say_batch_synthesize

        logger = logging.getLogger(__name__)

        if not tex_path.exists():
            return

        tex_content = tex_path.read_text(encoding="utf-8")
        num_frames = tex_content.count(r"\begin{frame}")
        if num_frames == 0:
            return

        # 用 LLM 生成讲解稿
        llm = get_llm(self.user_id)
        prompt = (
            f"以下是一份 LaTeX Beamer 知识卡片，共 {num_frames} 页。\n\n"
            f"请以老师的身份，为每一页写一段**简短的讲解旁白**（30-80字/页）。\n"
            f"要求口语化、启发式，不复读幻灯片文字。\n"
            f"输出 JSON 数组，长度等于 {num_frames}，每项为字符串。\n\n"
            f"```tex\n{tex_content[:6000]}\n```"
        )
        response = llm.think(
            [
                {"role": "system", "content": "你是一位亲切的老师，只输出 JSON 数组。"},
                {"role": "user", "content": prompt},
            ],
            config={"temperature": 0.5, "max_tokens": 2000},
        )

        match = re.search(r"\[[\s\S]*\]", response.content)
        if not match:
            return
        try:
            notes = json.loads(match.group())
            if not isinstance(notes, list):
                return
        except Exception:  # pylint: disable=broad-except
            return

        # TTS 合成
        audio_dir = CARDS_DIR / card_id / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        items = [
            {"text": str(note), "filename": f"frame_{i + 1:03d}.wav"}
            for i, note in enumerate(notes)
        ]
        result = say_batch_synthesize(
            items=items, output_dir=str(audio_dir), voice="Tingting", rate=180
        )

        # 保存讲解稿
        notes_path = CARDS_DIR / card_id / "notes.json"
        notes_path.write_text(
            json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info(
            "卡片 %s TTS 完成：%d 段语音", card_id, len(result.get("results", []))
        )
