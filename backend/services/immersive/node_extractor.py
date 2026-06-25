"""知识图谱节点抽取（LLM + DB 写入）。"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

from agent_core.llm.base import BaseLLM

from models.node import NodeContent, NodeCreate, NodeOrigin
from repositories import NodeRepository

logger = logging.getLogger(__name__)


def extract_and_persist_nodes(
    session_id: str,
    topic: str,
    chapters: List[Dict],
    llm: Optional[BaseLLM],
    user_id: str,
) -> List[Dict[str, str]]:
    """从章节知识点中抽取知识图谱节点并写入 nodes 表。

    返回值：[{id, title, existed}, ...]，existed=True 表示该节点之前已存在。
    """
    all_kps = []
    for ch in chapters:
        for kp in ch.get("knowledge_points", []):
            all_kps.append({"kp": kp, "chapter": ch.get("title", "")})
    if not all_kps:
        return []

    if llm is None:
        logger.warning("知识图谱抽取已跳过：未提供可用的 LLM 实例（llm=None）")
        return []

    kp_text = "\n".join(f"- [{item['chapter']}] {item['kp']}" for item in all_kps)
    chapter_count = len(chapters)
    max_nodes = min(20, max(5, chapter_count * 3))

    prompt = (
        f"以下是「{topic}」课程各章节的知识点列表（格式：[章节] 知识点）：\n"
        f"{kp_text}\n\n"
        "请把这些知识点整理为可独立复习的知识图谱节点。\n\n"
        "## 节点粒度（最重要）\n"
        "**一个节点 = 一个独立概念**。\n"
        "- ✅ 正例：「极限」「导数」「二叉树」「快速排序」\n"
        "- ❌ 反例：「极限和导数」「栈与队列」「TCP/UDP 协议」——复合概念必须拆成多个节点\n"
        "- 同一章节内若出现多个独立概念，分别建节点；跨章节出现的同一概念才合并去重\n\n"
        "## 字段要求\n"
        '- `title`：单一概念名，不含"和/与/及/、/," 等并列词；不要带章节前缀\n'
        "- `description`：50 字以内，独立可读，**不要使用「它」「该」等代词**，开头直接给定义\n"
        "- `tags`：1-3 个标签，必须来自课程主题「"
        + topic
        + "」或章节标题，不要新造词\n"
        "- `key_points`：3-5 条，每条是一个可考核的事实/性质/步骤，不要与 description 重复\n\n"
        "## 数量与质量\n"
        f"- 共产出 {max(5, chapter_count)}-{max_nodes} 个节点；宁缺毋滥，每个节点都要值得单独复习\n"
        "- 仅保留有独立学习价值的核心概念，琐碎术语不建节点\n\n"
        "## 输出格式（严格遵守）\n"
        "直接输出 JSON 数组，**不要**用 ```json 围栏，**不要**任何解释文字。\n"
        "数组每项结构：\n"
        '{"title": "概念名", "description": "定义...", "tags": ["..."], "key_points": ["...", "..."]}'
    )
    try:
        response = llm.think(
            [
                {
                    "role": "system",
                    "content": (
                        "你是知识图谱构建专家。你的产出会直接写入用户的个人知识图谱供长期复习使用，"
                        "因此每个节点都必须是单一、独立、可考核的概念。只输出 JSON 数组，不要任何额外文字。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            config={"temperature": 0.3, "max_tokens": 3000},
        )
        match = re.search(r"\[[\s\S]*\]", response.content)
        if not match:
            return []
        nodes_data = json.loads(match.group())
        if not isinstance(nodes_data, list):
            return []
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("知识图谱抽取 LLM 调用失败: %s", e)
        return []

    created_nodes: List[Dict[str, str]] = []
    node_repo = NodeRepository()
    for nd in nodes_data[:max_nodes]:
        title = nd.get("title", "").strip()
        if not title:
            continue

        # 查重节点
        existing_id = node_repo.find_by_title(user_id, title)
        if existing_id:
            created_nodes.append({"id": existing_id, "title": title, "existed": True})
            continue

        description = nd.get("description", "")
        data = NodeCreate(
            title=title,
            description=description,
            tags=nd.get("tags", [topic]),
            content=NodeContent(
                summary=description,
                key_points=nd.get("key_points", []),
                examples=[],
                common_mistakes=[],
            ),
            origins=[
                NodeOrigin(
                    source_type="session",
                    source_id=session_id,
                    source_title=f"[AI课程] {topic}",
                    location="AI课程自动抽取",
                    excerpt=description[:200],
                )
            ],
        )
        node = node_repo.create(user_id, data, initial_mastery=0.1)
        created_nodes.append({"id": node.id, "title": title, "existed": False})

    logger.info("知识图谱抽取完成：%d 个节点", len(created_nodes))
    return created_nodes
