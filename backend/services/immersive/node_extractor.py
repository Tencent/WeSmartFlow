"""知识图谱节点抽取（LLM + DB 写入）。"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List

from agent_core.llm.base import BaseLLM

from models.node import NodeContent, NodeCreate, NodeOrigin
from repositories import NodeRepository

logger = logging.getLogger(__name__)


def extract_and_persist_nodes(
    session_id: str,
    topic: str,
    chapters: List[Dict],
    llm: BaseLLM,
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

    kp_text = "\n".join(f"- [{item['chapter']}] {item['kp']}" for item in all_kps)
    prompt = (
        f"以下是关于「{topic}」课程各章节的知识点列表：\n{kp_text}\n\n"
        "请整理为知识图谱节点，要求：\n"
        "1. 去重合并相似概念\n2. 为每个节点提供简洁描述（50字内）\n"
        "3. 标注所属标签\n4. 严格输出 JSON 数组，每项：\n"
        '   {"title": "概念名", "description": "描述", "tags": ["标签"], "key_points": ["要点"]}\n'
        "5. 数量 5-15 个核心概念\n直接输出 JSON 数组。"
    )
    try:
        response = llm.think(
            [
                {"role": "system", "content": "你是知识图谱构建专家，只输出 JSON。"},
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
    for nd in nodes_data[:15]:
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
