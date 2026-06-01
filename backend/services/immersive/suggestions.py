"""
个性化推荐云朵生成器

根据用户画像（profile.md）和学习历史（mastery.json + courses 列表），
调用 LLM 生成个性化的推荐主题标签，用于首页飘浮云朵展示。

推荐策略：
1. 薄弱知识点 → 建议巩固
2. 已学主题的进阶方向 → 建议深入
3. 基于用户兴趣/背景推荐新领域
4. 新用户 → 返回空列表，前端使用默认标签
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from config import DOCUMENTS_DIR
from services.llm_factory import get_llm

logger = logging.getLogger(__name__)

# 缓存：避免每次登录都调用 LLM（缓存 10 分钟）
_suggestions_cache: Dict[str, Dict[str, Any]] = {}  # user_id -> {data, timestamp}
_CACHE_TTL_SECONDS = 600  # 10 分钟


async def generate_suggestions(user_id: str) -> Dict[str, Any]:
    """生成个性化推荐云朵内容。

    Returns:
        {
            "suggestions": [{"text": ..., "emoji": ..., "size": ..., "reason": ...}, ...],
            "source": "personalized" | "default"
        }
    """
    import time

    # 检查缓存
    cached = _suggestions_cache.get(user_id)
    if cached and (time.time() - cached["timestamp"]) < _CACHE_TTL_SECONDS:
        return cached["data"]

    # 读取用户画像（按 user_id 隔离）
    profile_content = _read_profile(user_id)
    # 读取 mastery.json（按 user_id 隔离）
    mastery_data = _read_mastery(user_id)
    # 读取学习历史（已完成的课程主题）
    learned_topics = _get_learned_topics(user_id)

    # 如果没有任何画像数据，返回默认
    if not profile_content and not mastery_data.get("topics") and not learned_topics:
        return {"suggestions": [], "source": "default"}

    # 调用 LLM 生成推荐
    try:
        suggestions = await _call_llm_for_suggestions(
            user_id, profile_content, mastery_data, learned_topics
        )
        if suggestions:
            result = {"suggestions": suggestions, "source": "personalized"}
            # 写入缓存
            _suggestions_cache[user_id] = {"data": result, "timestamp": time.time()}
            return result
        else:
            return {"suggestions": [], "source": "default"}
    except Exception as e:
        logger.warning("LLM 生成推荐失败: %s", e)
        return {"suggestions": [], "source": "default"}


def _read_profile(user_id: str = "") -> str:
    """读取指定用户的 profile.md 内容。"""
    from agent_core.layout import UserDataLayout

    layout = UserDataLayout(root=DOCUMENTS_DIR, user_id=user_id)
    if layout.profile_file.exists():
        content = layout.profile_file.read_text(encoding="utf-8").strip()
        return content
    # fallback: 尝试读取旧的全局画像（迁移兼容）
    if user_id:
        legacy_file = Path(DOCUMENTS_DIR) / "profile" / "profile.md"
        if legacy_file.exists():
            return legacy_file.read_text(encoding="utf-8").strip()
    return ""


def _read_mastery(user_id: str = "") -> Dict[str, Any]:
    """读取指定用户的 mastery.json。"""
    from agent_core.layout import UserDataLayout

    layout = UserDataLayout(root=DOCUMENTS_DIR, user_id=user_id)
    mastery_file = layout.mastery_file
    if mastery_file.exists():
        try:
            return json.loads(mastery_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    # fallback: 尝试读取旧的全局文件（迁移兼容）
    if user_id:
        legacy_file = Path(DOCUMENTS_DIR) / "profile" / "mastery.json"
        if legacy_file.exists():
            try:
                return json.loads(legacy_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    return {"topics": {}}


def _get_learned_topics(user_id: str) -> List[str]:
    """从 sessions 表获取用户已学过的课程主题。"""
    try:
        from database import get_db

        topics = []
        with get_db() as conn:
            cur = conn.execute(
                "SELECT topic, title FROM sessions WHERE user_id = ? AND status = 'completed'",
                (user_id,),
            )
            for row in cur.fetchall():
                topic = row["topic"] or row["title"] or ""
                topic = topic.replace("[AI课程]", "").strip()
                if topic:
                    topics.append(topic)
        return topics
    except Exception:
        return []


async def _call_llm_for_suggestions(
    user_id: str,
    profile_content: str,
    mastery_data: Dict[str, Any],
    learned_topics: List[str],
) -> List[Dict[str, str]]:
    """调用 LLM 生成推荐主题列表。"""

    # 构建上下文
    context_parts = []

    if profile_content:
        context_parts.append(f"## 用户画像\n{profile_content}")

    if learned_topics:
        context_parts.append("## 已学过的课程\n" + "、".join(learned_topics))

    topics_data = mastery_data.get("topics", {})
    if topics_data:
        mastery_lines = []
        for topic_name, topic_info in topics_data.items():
            chapters = topic_info.get("chapters", {})
            if chapters:
                accuracies = [ch.get("accuracy", 0) for ch in chapters.values()]
                avg_acc = sum(accuracies) / len(accuracies) if accuracies else 0
                status = (
                    "熟练"
                    if avg_acc >= 0.8
                    else "基本掌握"
                    if avg_acc >= 0.6
                    else "需要加强"
                )
                mastery_lines.append(
                    f"- {topic_name}：{status}（正确率 {avg_acc:.0%}）"
                )
            else:
                mastery_lines.append(f"- {topic_name}：已学习，待评价")
        context_parts.append("## 知识点掌握情况\n" + "\n".join(mastery_lines))

    context = "\n\n".join(context_parts)

    system_prompt = """你是一个智能学习推荐系统。根据用户的画像和学习历史，推荐 8-12 个学习主题。

推荐策略：
1. 如果用户有薄弱知识点（正确率低），推荐相关的巩固主题（标注为巩固类）
2. 如果用户已掌握某些主题，推荐进阶方向（标注为进阶类）
3. 根据用户的学习背景和兴趣，推荐新的探索方向（标注为探索类）
4. 推荐的主题应该多样化，涵盖不同领域
5. 每个主题名称要简洁（2-6个字），适合作为标签展示

你必须严格按照以下 JSON 格式输出，不要输出其他内容：
```json
[
  {"text": "主题名", "emoji": "合适的emoji", "size": "xl|lg|md|sm|xs", "reason": "一句话推荐理由"}
]
```

size 规则：
- xl: 最重要/最推荐的（1-2个）
- lg: 比较推荐的（2-3个）
- md: 一般推荐（3-4个）
- sm: 可选探索（2-3个）
- xs: 轻度推荐（1-2个）

emoji 要求：选择与主题最相关的 emoji，让标签更生动。"""

    user_prompt = f"""请根据以下用户信息，生成个性化的学习主题推荐：

{context}

请生成 8-12 个推荐主题，严格按 JSON 数组格式输出。"""

    llm = get_llm(user_id)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    response = await llm.async_think(
        messages, config={"temperature": 0.8, "max_tokens": 1024}
    )

    if not response or not response.content or response.is_error:
        logger.warning("LLM 推荐生成返回空或错误")
        return []

    # 解析 JSON 响应
    content = response.content.strip()
    # 尝试提取 JSON 数组（可能被 ```json ``` 包裹）
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    try:
        suggestions = json.loads(content)
        if not isinstance(suggestions, list):
            logger.warning("LLM 返回的不是数组: %s", content[:200])
            return []

        # 验证和清洗数据
        valid_sizes = {"xl", "lg", "md", "sm", "xs"}
        cleaned = []
        for item in suggestions[:12]:  # 最多取 12 个
            if not isinstance(item, dict) or "text" not in item:
                continue
            cleaned.append(
                {
                    "text": str(item.get("text", ""))[:10],  # 限制长度
                    "emoji": str(item.get("emoji", "📚"))[:4],
                    "size": item.get("size", "md")
                    if item.get("size") in valid_sizes
                    else "md",
                    "reason": str(item.get("reason", ""))[:30],
                }
            )

        return cleaned

    except json.JSONDecodeError as e:
        logger.warning("LLM 推荐结果 JSON 解析失败: %s, content: %s", e, content[:200])
        return []


def invalidate_cache(user_id: str) -> None:
    """清除指定用户的推荐缓存（画像更新后调用）。"""
    _suggestions_cache.pop(user_id, None)
