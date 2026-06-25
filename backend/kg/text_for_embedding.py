"""
统一构建写入向量库的 embedding 文本。

设计目标：
- 模板化：每类实体一个固定结构化模板，role 标签用英文 key（name/aliases/...）
- 带上下文：facet 会带 primary_concept 的名字 + 一句话定义
- 截断统一为 8000 字符
- 软依赖：所有输入都用 .get/.getattr 容错，缺字段不抛

调用方约定：
- concept: build_concept_text(concept)
- facet:   build_facet_text(facet, concept=None)

所有函数都返回 str，永远不抛异常。
"""

from __future__ import annotations

from typing import Any

# 单条 embedding 文本的最大字符数（保守按 1 字 ≈ 1 token 估算，留裕量）
MAX_CHARS = 8000


# ============================================================
# 通用工具
# ============================================================


def _to_dict(obj: Any) -> dict:
    """把 Pydantic / dataclass / dict 统一成 dict，方便 .get 访问。"""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:  # noqa: BLE001
            pass
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:  # noqa: BLE001
            pass
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return {}


def _truncate(text: str, max_chars: int = MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _join_lines(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line and line.strip())


# ============================================================
# Concept
# ============================================================


def build_concept_text(concept: Any) -> str:
    """
    概念 → embedding 文本。

    模板：
        name: <canonical_name>
        canonical: <canonical_name>
        subject: <subject>
        aliases (zh): ...
        aliases (en): ...
        aliases (notation): ...
        tags: ...
        summary: <summary>
    """
    c = _to_dict(concept)
    canonical = (c.get("canonical_name") or "").strip()
    subject = (c.get("subject") or "").strip()
    summary = (c.get("summary") or "").strip()
    tags = c.get("tags") or []
    aliases_raw = c.get("aliases") or []

    zh_aliases: list[str] = []
    en_aliases: list[str] = []
    notation_aliases: list[str] = []
    other_aliases: list[str] = []

    for a in aliases_raw:
        a_dict = _to_dict(a)
        name = (a_dict.get("name") or "").strip()
        if not name or name == canonical:
            continue
        lang = (a_dict.get("lang") or "").lower().strip()
        if lang == "zh":
            zh_aliases.append(name)
        elif lang == "en":
            en_aliases.append(name)
        elif lang in ("notation", "symbol", "math"):
            notation_aliases.append(name)
        else:
            other_aliases.append(name)

    lines = [
        f"name: {canonical}" if canonical else "",
        f"canonical: {canonical}" if canonical else "",  # 主名重复一次：加权
        f"subject: {subject}" if subject else "",
    ]
    if zh_aliases:
        lines.append(f"aliases (zh): {', '.join(zh_aliases)}")
    if en_aliases:
        lines.append(f"aliases (en): {', '.join(en_aliases)}")
    if notation_aliases:
        lines.append(f"aliases (notation): {', '.join(notation_aliases)}")
    if other_aliases:
        lines.append(f"aliases: {', '.join(other_aliases)}")
    if tags:
        lines.append(f"tags: {', '.join(str(t) for t in tags if t)}")
    if summary:
        lines.append(f"summary: {summary}")

    return _truncate(_join_lines(lines))


# ============================================================
# Facet（切面 → embedding 文本）
# ============================================================


def build_facet_text(facet: Any, concept: Any = None) -> str:
    """
    切面 → embedding 文本。

    模板：
        kind: <kind>
        concept: <canonical_name> — <summary>
        content: <content>
        notes: <extra.notes>   # 可选
    """
    f = _to_dict(facet)
    kind = (f.get("kind") or "").strip()
    content = (f.get("content") or "").strip()
    extra = f.get("extra") or {}

    lines: list[str] = []
    if kind:
        lines.append(f"kind: {kind}")

    pc = _to_dict(concept)
    if pc:
        canon = (pc.get("canonical_name") or "").strip()
        sd = (pc.get("summary") or "").strip()
        if canon and sd:
            lines.append(f"concept: {canon} — {sd}")
        elif canon:
            lines.append(f"concept: {canon}")

    if content:
        lines.append(f"content: {content}")

    # extra 里允许的少量补充
    if isinstance(extra, dict):
        notes = (
            (extra.get("notes") or "").strip()
            if isinstance(extra.get("notes"), str)
            else ""
        )
        if notes:
            lines.append(f"notes: {notes}")

    return _truncate(_join_lines(lines))
