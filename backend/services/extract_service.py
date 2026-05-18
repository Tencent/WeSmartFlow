"""
ExtractService：从文档提取知识节点

流程：
1. 读取文档文本（PDF/txt/md）
2. 构建 ExtractAgent（注册工具、ContextBuilder、SkillsLoader）
3. Agent 自主分析 → 搜索去重 → 创建节点并建立关系
4. 更新 document.node_ids 和 document.status
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Any

from agent_core.builtins import BUILTIN_SKILLS_DIR
from agent_core.skills.loader import SkillsLoader
from agent_core.tool.filesystem import ReadFileTool, ListDirTool
from agent_core.tool.registry import ToolRegistry
from agents import ChatAgent
from agent_core.context import SkillPromptContextBuilder
from agents.tools.create_node import DocumentCreateNodeTool
from agents.tools.search_nodes import SearchNodesTool
from repositories import DocumentRepository
from repositories.node_repo import NodeRepository
from services.llm_factory import get_llm

logger = logging.getLogger(__name__)

# agents 专属 skills 目录
_AGENTS_SKILLS_DIR = Path(__file__).parent.parent / "agents" / "prompts" / "skills"


class ExtractService:
    def __init__(self):
        self.doc_repo = DocumentRepository()
        self.node_repo = NodeRepository()

    async def extract(self, user_id: str, doc_id: str) -> list[str]:
        """用 ExtractAgent 提取文档中的知识节点，返回新创建的 node_id 列表。"""
        doc = self.doc_repo.get_by_id(doc_id)
        if not doc:
            raise ValueError(f"文档 {doc_id} 不存在")

        self.doc_repo.set_status(doc_id, "processing")

        try:
            # 读取文档内容
            file_path = Path(doc.get_file_path())
            text = self._read_file(str(file_path), doc.file_type)

            # 根据文档大小选择处理策略
            if len(text) > 10000:  # 大文档使用分段处理
                node_ids = await self._process_large_document(
                    user_id, doc_id, doc.title, doc.file_type, text
                )
            else:  # 小文档直接使用强Agent处理
                node_ids = await self._run_strong_agent(
                    user_id, doc_id, doc.title, doc.file_type, text
                )

            self.doc_repo.set_node_ids(doc_id, node_ids)
            self.doc_repo.set_status(doc_id, "ready")
            # 短连接模式下 _execute 已自动 commit

            return node_ids
        except Exception as e:
            logger.exception("文档提取失败: %s", doc_id)
            self.doc_repo.set_status(doc_id, "failed", str(e))
            # 短连接模式下 _execute 已自动 commit
            raise

    async def _process_large_document(
        self, user_id: str, doc_id: str, doc_title: str, doc_type: str, text: str
    ) -> list[str]:
        """处理大型文档：分段提取"""
        segments = self._segment_document(text, doc_type)
        all_new_node_ids = []

        logger.info("开始分段处理文档 %s，共 %d 个段落", doc_id, len(segments))

        for i, segment in enumerate(segments):
            try:
                # 为每个段落创建上下文
                segment_context = f"段落 {i + 1}/{len(segments)}: {segment['title']}"

                # 使用强Agent处理每个段落
                segment_node_ids = await self._run_strong_agent(
                    user_id,
                    doc_id,
                    f"{doc_title} - {segment['title']}",
                    doc_type,
                    segment["content"],
                    segment_context,
                )

                all_new_node_ids.extend(segment_node_ids)

                logger.info(
                    "段落 %d 处理完成，新增 %d 个节点", i + 1, len(segment_node_ids)
                )

            except Exception as e:  # pylint: disable=broad-except
                logger.warning("段落 %d 处理失败: %s", i + 1, e)
                continue

        return all_new_node_ids

    async def _run_strong_agent(
        self,
        user_id: str,
        doc_id: str,
        doc_title: str,
        doc_type: str,
        text: str,
        context: str = "",
    ) -> list[str]:
        # 使用hook机制来准确统计新增节点
        new_node_ids = []

        def _node_creation_hook(
            tool_name: str, params: Dict[str, Any], result: Any
        ) -> None:
            """节点创建hook，用于准确统计新增节点"""
            if tool_name == "create_node":
                try:
                    data = json.loads(result) if isinstance(result, str) else result
                    if data.get("created"):
                        new_node_ids.append(data["node_id"])
                        logger.info("文档 %s 新增节点: %s", doc_id, data["node_id"])
                except (json.JSONDecodeError, AttributeError):
                    pass

        # 组装强大的工具集，使用hook机制
        tools = [
            SearchNodesTool(user_id=user_id),
            DocumentCreateNodeTool(
                user_id=user_id,
                document_id=doc_id,
                on_result_hook=_node_creation_hook,
            ),
            ReadFileTool(
                allowed_dir=BUILTIN_SKILLS_DIR,
                extra_allowed_dirs=[_AGENTS_SKILLS_DIR],
            ),
            ListDirTool(
                allowed_dir=BUILTIN_SKILLS_DIR,
                extra_allowed_dirs=[_AGENTS_SKILLS_DIR],
            ),
        ]

        # 使用更强的上下文构建器
        context_builder = SkillPromptContextBuilder(
            prompt_file=Path(__file__).parent.parent
            / "agents"
            / "prompts"
            / "extract_enhanced.md",
            skills_loader=SkillsLoader(workspace_skills_dir=_AGENTS_SKILLS_DIR),
        )

        agent = ChatAgent(
            llm=get_llm(user_id),
            context_builder=context_builder,
            tool_registry=ToolRegistry(tools),
            max_steps=50,  # 增加最大步数以获得更深入的分析
            llm_config={"temperature": 0.1},  # 降低温度以获得更稳定的输出
        )

        # 构建更详细的用户输入
        title_hint = f"《{doc_title}》" if doc_title else "该文档"
        user_input = (
            f"请深入分析以下文档{title_hint}，提取核心知识节点并建立完整的知识图谱关系。"
            f"{context}\n\n"
            f"文档内容：\n---\n{text[:8000]}\n---"
            f"\n\n请确保："
            f"1. 识别关键概念、定义、原理"
            f"2. 提取重要示例和应用场景"
            f"3. 建立概念之间的关联关系"
            f"4. 标注知识点的难度级别"
        )

        summary = await agent.async_run(user_input)
        logger.info("[StrongAgent] 文档 %s 分析完成：%s", doc_id, summary.output[:100])

        logger.info("[StrongAgent] 文档 %s 新增节点 %d 个", doc_id, len(new_node_ids))
        return new_node_ids

    def _read_file(self, file_path: str, file_type: str) -> str:
        """读取文档文本内容"""
        # file_path 已经是绝对路径，直接使用
        full_path = Path(file_path)
        if file_type == "pdf":
            return self._read_pdf(full_path)
        return full_path.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _read_pdf(path: Path) -> str:
        try:
            import pdfplumber

            with pdfplumber.open(path) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
            return "\n\n".join(pages)
        except ImportError:
            raise RuntimeError("请安装 pdfplumber: pip install pdfplumber")

    def _segment_document(self, text: str, doc_type: str) -> list[dict]:
        """将文档内容分段，便于精确引用"""
        segments = []

        if doc_type == "pdf":
            # PDF按页面分段
            lines = text.split("\n\n")
            for i, page_content in enumerate(lines, 1):
                if page_content.strip():
                    segments.append(
                        {
                            "segment_id": f"page_{i}",
                            "type": "page",
                            "title": f"第{i}页",
                            "content": page_content,
                            "page_number": i,
                        }
                    )
        elif doc_type in ["txt", "md"]:
            # 文本文件按章节分段
            lines = text.split("\n")
            current_section = []
            section_title = "引言"
            section_id = 1

            for line in lines:
                # 检测章节标题（Markdown格式或大写标题）
                if line.startswith("# ") or (
                    len(line) > 20 and line.isupper() and line.strip()
                ):
                    if current_section:
                        segments.append(
                            {
                                "segment_id": f"section_{section_id}",
                                "type": "section",
                                "title": section_title,
                                "content": "\n".join(current_section),
                                "page_number": None,
                            }
                        )
                        section_id += 1
                    section_title = line.lstrip("# ").strip()
                    current_section = [line]
                else:
                    current_section.append(line)

            # 添加最后一个章节
            if current_section:
                segments.append(
                    {
                        "segment_id": f"section_{section_id}",
                        "type": "section",
                        "title": section_title,
                        "content": "\n".join(current_section),
                        "page_number": None,
                    }
                )
        else:
            # 其他格式按固定长度分段
            chunk_size = 1000
            for i in range(0, len(text), chunk_size):
                chunk = text[i : i + chunk_size]
                segments.append(
                    {
                        "segment_id": f"chunk_{i // chunk_size + 1}",
                        "type": "chunk",
                        "title": f"片段{i // chunk_size + 1}",
                        "content": chunk,
                        "page_number": None,
                    }
                )

        return segments

    # ------------------------------------------------------------------
    # 公开 API：供 router / 其他 service 使用
    # ------------------------------------------------------------------

    def read_content(self, file_path: str, file_type: str) -> str:
        """读取文档原始文本内容（公开接口）。

        包装内部 ``_read_file``，对外提供稳定的语义化入口，避免调用方依赖私有方法。
        """
        return self._read_file(file_path, file_type)

    def segment_content(self, text: str, doc_type: str) -> list[dict]:
        """将文档文本分段（公开接口）。

        包装内部 ``_segment_document``。
        """
        return self._segment_document(text, doc_type)

    def read_and_segment(
        self, file_path: str, file_type: str
    ) -> tuple[str, list[dict]]:
        """一次性读取文档内容并完成分段，便于 router 直接消费。

        Returns:
            ``(content, segments)`` 二元组。
        """
        content = self._read_file(file_path, file_type)
        segments = self._segment_document(content, file_type)
        return content, segments
