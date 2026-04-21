"""
GenerateCardTool：委派 CardWriterAgent（subagent）生成 PDF 知识卡片

Tutor Agent 只需描述"想展示什么内容"，CardWriterAgent 负责：
  1. 自主编写 Beamer .tex 源码
  2. 调用 latex_pdf_compile 编译 PDF
  3. 编译失败时自动修复重试

生成的 PDF 保存至 generated_cards/{uuid}.pdf，成功时返回相对于 CARDS_DIR 的相对路径。
"""

from __future__ import annotations

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
from config import CARDS_DIR
from services.llm_factory import get_llm


# CardWriterAgent 的 system prompt
_CARD_WRITER_SYSTEM_PROMPT = """你是精通 LaTeX Beamer 的卡片设计师，专注生成轻量、精炼的知识卡片。

## 工作流程

1. 按照用户要求的页数上限规划内容，**严格不超过指定的内容页数**
2. 如需插图，先调用 generate_teaching_image 生成图片到工作目录，再在 tex 中引用
3. 用 write_file 将完整 .tex 写入指定路径
4. 用 latex_pdf_compile 编译 PDF
5. 编译失败时根据错误日志修复后重试（最多 2 次）
6. 编译成功后简要说明已完成，无需输出文件路径

## 页数约束（最重要）

- 用户会在指令中指定 max_pages（页数上限，1-3）
- **页面总数必须 ≤ max_pages，宁可少不可多**
- 每页不超过 6 行文字，保持简洁

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


def _build_image_tool() -> OpenAIImageGenTool:
    """从 settings 表读取图像生成配置，构建 OpenAIImageGenTool 实例。

    如果配置读取失败，仍返回一个可用的实例（使用默认值），
    确保不会因为图片生成配置问题而阻断卡片生成流程。
    """
    try:
        from database import get_setting
        import os

        api_key = get_setting("img_api_key") or os.getenv("IMG_API_KEY", "any")
        base_url = get_setting("img_base_url") or os.getenv(
            "IMG_BASE_URL", "http://localhost:8080/v1"
        )
        model = get_setting("img_model") or os.getenv("IMG_MODEL") or None
    except Exception as e:  # pylint: disable=broad-except
        import logging
        import os

        logging.getLogger(__name__).warning(
            "图片生成配置读取失败（将使用默认值，图片功能可能不可用）: %s", e
        )
        api_key = os.getenv("IMG_API_KEY", "any")
        base_url = os.getenv("IMG_BASE_URL", "http://localhost:8080/v1")
        model = os.getenv("IMG_MODEL") or None
    return OpenAIImageGenTool(api_key=api_key, base_url=base_url, model=model)


def _build_card_writer_agent(work_dir: Path) -> ReActAgent:
    """创建 CardWriterAgent，工作目录限定在 work_dir 下，支持插图生成。"""
    tools = ToolRegistry(
        [
            WriteFileTool(workspace=work_dir, allowed_dir=work_dir),
            _build_image_tool(),
            LatexPdfCompileTool(),
        ]
    )
    return ReActAgent(
        llm=get_llm(),
        context_builder=SimpleContextBuilder(_CARD_WRITER_SYSTEM_PROMPT),
        tool_registry=tools,
        max_steps=15,
        llm_config={"temperature": 0.3},
    )


class GenerateCardTool(BaseTool):
    """
    委派 CardWriterAgent 生成 PDF 知识卡片（Beamer + SimplePlus 主题）。

    Tutor Agent 描述想展示的内容，CardWriterAgent 负责编写 tex、编译 PDF。
    成功时返回相对于 CARDS_DIR 的相对路径（如 {uuid}.pdf），失败时返回 Error: 开头的错误信息。
    """

    name = "generate_card"
    description = (
        "委派专门的卡片生成 Agent 制作一张轻量 PDF 知识卡片（Beamer 风格，支持插图）。"
        "每次只生成 1-3 页内容，适合聚焦单个知识点、对比或步骤。"
        "描述你想展示的内容即可，卡片的排版、插图和编译由子 Agent 负责。"
        "成功时返回相对路径（如 {uuid}.pdf），失败时返回 Error: 开头的错误信息。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "卡片标题，简洁有力，如'快速排序 — 核心思路'",
            },
            "content_description": {
                "type": "string",
                "description": (
                    "描述卡片需要展示的内容，越详细越好。"
                    "例如：核心概念、关键要点、对比项、算法步骤、公式等。"
                    "子 Agent 会据此自主设计卡片结构和排版。"
                ),
            },
            "max_pages": {
                "type": "integer",
                "description": "页数上限，取值 1-3，默认 2。聚焦单概念用 1，需要对比或步骤用 2-3。",
            },
            "node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "关联的知识节点ID列表，用于建立文档与节点的链接",
            },
        },
        "required": ["title", "content_description"],
    }

    def __init__(self, db=None, user_id=None, session_id=None, on_result_hook=None):
        super().__init__(on_result_hook=on_result_hook)
        self.db = db
        self.user_id = user_id
        self.session_id = session_id

    def run(
        self,
        title: str,
        content_description: str,
        max_pages: int = 2,
        node_ids: list = None,
        **_,
    ) -> str:
        max_pages = max(1, min(3, int(max_pages)))  # 硬性限制 1-3
        card_id = str(uuid.uuid4())
        # 使用系统临时目录隔离 subagent 编译中间产物，退出 with 块后自动清理
        with tempfile.TemporaryDirectory(prefix=f"card_{card_id}_") as _tmp:
            work_dir = Path(_tmp)
            result = self._run_agent(
                card_id, work_dir, title, content_description, max_pages
            )

            # 如果生成成功，创建文档记录
            if not result.startswith("Error") and result.endswith(".pdf"):
                self._create_document_record(
                    card_id, result, title, content_description, node_ids
                )

            return result

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
            from repositories.document_repo import DocumentRepository
            import os
            from config import CARDS_DIR

            if not self.db:
                print("警告：数据库连接未设置，跳过文档记录创建")
                return

            doc_repo = DocumentRepository(self.db)

            # 获取实际文件大小
            pdf_path = CARDS_DIR / file_name
            file_size = os.path.getsize(pdf_path) if pdf_path.exists() else 0

            # 创建文档记录
            doc = doc_repo.create_generated(
                doc_id=card_id,
                user_id=self.user_id or "default",
                title=title,
                file_name=file_name,
                file_type="pdf",
                file_size=file_size,
                generation_prompt=content_description,
                generation_context=f"由TutorAgent在会话{self.session_id}中生成"
                if self.session_id
                else "由GenerateCardTool生成",
                session_id=self.session_id,
                node_ids=node_ids or [],
            )

            print(f"卡片文档记录创建成功: {doc.id}")

        except Exception as e:  # pylint: disable=broad-except
            print(f"创建卡片文档记录失败: {e}")

    def _run_agent(
        self,
        card_id: str,
        work_dir: Path,
        title: str,
        content_description: str,
        max_pages: int,
    ) -> str:
        try:
            tmp_tex = work_dir / "card.tex"
            tmp_pdf = work_dir / "card.pdf"

            # 组装给 subagent 的指令，限定其在 work_dir 下工作
            instruction = (
                f"请生成一张标题为「{title}」的 PDF 知识卡片。\n\n"
                f"内容要求：\n{content_description}\n\n"
                f"【页数约束】页面总数不超过 {max_pages} 页，严格执行。\n\n"
                f"工作目录：{work_dir}\n"
                f"tex 文件路径：{tmp_tex}\n"
                f"编译完成后 PDF 路径应为：{tmp_pdf}\n"
                f"如需插图，调用 generate_teaching_image 并将 output_dir 设为：{work_dir}\n\n"
                f"所有文件必须写在工作目录 {work_dir} 下，不得写到其他位置。"
            )

            # 调用 CardWriterAgent（同步），工作目录限定
            agent = _build_card_writer_agent(work_dir)
            result = agent.run(instruction)
            output = result.output or ""

            if not tmp_pdf.exists():
                return f"Error: 卡片生成失败 — {output}"

            # 由代码硬性将产物移动到最终位置，命名为 {uuid}.tex / {uuid}.pdf
            final_tex = CARDS_DIR / f"{card_id}.tex"
            final_pdf = CARDS_DIR / f"{card_id}.pdf"
            if tmp_tex.exists():
                shutil.move(str(tmp_tex), str(final_tex))

            shutil.move(str(tmp_pdf), str(final_pdf))

            # ── TTS 语音讲解生成 ──────────────────────────────────
            try:
                self._generate_card_audio(card_id, final_tex, final_pdf)
            except Exception as tts_err:  # pylint: disable=broad-except
                import logging

                logging.getLogger(__name__).warning("卡片 TTS 生成失败: %s", tts_err)

            # ── 资产归档到 data/assets/ ──────────────────────────
            try:
                from services.asset_service import archive_pdf, archive_audio

                # 归档 PDF
                archive_pdf(
                    final_pdf,
                    title=title,
                    source_type="card",
                    session_id=self.session_id or "",
                )
                # 归档 TTS 音频
                audio_dir = CARDS_DIR / f"{card_id}_audio"
                if audio_dir.exists():
                    notes_path = CARDS_DIR / f"{card_id}_notes.json"
                    notes = []
                    if notes_path.exists():
                        import json as _json

                        try:
                            notes = _json.loads(notes_path.read_text(encoding="utf-8"))
                        except Exception:  # pylint: disable=broad-except
                            pass
                    for wav in sorted(audio_dir.glob("*.wav")):
                        import re as _re

                        m = _re.match(r"frame_(\d+)", wav.stem)
                        frame_idx = int(m.group(1)) if m else 0
                        text = (
                            notes[frame_idx - 1] if 0 < frame_idx <= len(notes) else ""
                        )
                        archive_audio(
                            wav,
                            text=text,
                            source_type="card",
                            chapter=card_id,
                            frame_index=frame_idx,
                        )
                import logging as _log

                _log.getLogger(__name__).info("卡片 %s 资产归档完成", card_id)
            except Exception as arch_err:  # pylint: disable=broad-except
                import logging as _log

                _log.getLogger(__name__).warning(
                    "卡片 %s 资产归档失败: %s", card_id, arch_err
                )

            return str(f"{card_id}.pdf")  # 直接返回这个

        except Exception as e:  # pylint: disable=broad-except
            return f"Error: 生成卡片失败 — {e}"

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
        llm = get_llm()
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
        audio_dir = CARDS_DIR / f"{card_id}_audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        items = [
            {"text": str(note), "filename": f"frame_{i + 1:03d}.wav"}
            for i, note in enumerate(notes)
        ]
        result = say_batch_synthesize(
            items=items, output_dir=str(audio_dir), voice="Tingting", rate=180
        )

        # 保存讲解稿
        notes_path = CARDS_DIR / f"{card_id}_notes.json"
        notes_path.write_text(
            json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info(
            "卡片 %s TTS 完成：%d 段语音", card_id, len(result.get("results", []))
        )
