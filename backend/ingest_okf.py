"""OKF Bundle → KG 增量同步器（重构版）

功能
====
扫描项目根目录下的 ``knowledge/`` 目录，把每个 ``.md`` 文件视作一个 OKF
concept 录入 KG（status=approved, origin=okf）：

  - frontmatter (YAML) 提供概念元数据 + 结构化关系字段
  - body 按 ``# H1`` 切段，每段成为一条 facet（kind = H1 标题原文）
  - 关系字段（prerequisites / generalizes / related ...）映射成 concept_edge

策略
====
- **增量同步（默认）**：根据 .md 文件的 sha256（存在 concept.source_hash）做 diff，
  只重写实际变化的部分，未变化的 concept/facet/edge 完全不动，节省向量 API 调用。
- **全量重建**：``--rebuild`` 模式下先删 KG 中所有 ``origin='okf'`` 的 facet/edge
  和 ``created_by='okf'`` 的 concept，再按 OKF 文件重建（早期开发期常用）。
- 飞轮数据（dialog_aggregated / agent_authored）完全不受影响。
- 失败可观测：parse 错 / slug 重复 / 关系断链 都打报告，但不阻塞整体。

运行
====
    conda run -n edu-agent python -m backend.ingest_okf            # 增量同步（默认）
    conda run -n edu-agent python -m backend.ingest_okf --rebuild  # 全量重建
    conda run -n edu-agent python -m backend.ingest_okf --dry-run  # 试运行
    conda run -n edu-agent python -m backend.ingest_okf --root my_kb  # 指定根
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from backend.kg.database import get_kg_db, init_kg_db
from backend.kg.models import (
    VALID_RELATION_TYPES,
    ConceptAlias,
    ConceptCreate,
    ConceptEdgeCreate,
    FacetCreate,
)
from backend.kg.repositories import (
    ConceptEdgeRepository,
    ConceptRepository,
    FacetRepository,
)
from backend.kg.repositories.base import (
    derive_concept_id,
    derive_edge_id,
    derive_facet_id,
)

logger = logging.getLogger(__name__)


# frontmatter 字段 → KG concept_edge.relation_type
REL_KEYS = {
    "prerequisites": "prerequisite",
    "generalizes": "generalizes",
    "special_case_of": "special_case_of",
    "equivalent_to": "equivalent_to",
    "part_of": "part_of",
    "application_of": "application_of",
    "contrasts": "contrasts",
    "related": "related",
}

# `# H1` 切段：MULTILINE，捕获标题
H1_RE = re.compile(r"^#\s+(.+)$", flags=re.MULTILINE)

# YAML frontmatter 检测：以 --- 开头并以单独一行 --- 结束
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", flags=re.DOTALL)


# ============================================================
# 解析
# ============================================================


def _file_hash(text: str) -> str:
    """对 .md 整文件文本做 sha256，返回十六进制串。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """从 markdown 文本里抽 YAML frontmatter，返回 (meta, body)。

    无 frontmatter → ({}, 原文)。
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw = m.group(1)
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML frontmatter 解析失败: {exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError("frontmatter 必须是 YAML 映射")
    body = text[m.end() :]
    return meta, body


def split_h1(body: str) -> list[tuple[str, str]]:
    """按 ``# H1`` 切，返回 ``[(title, content)]``。第一个 H1 之前的内容丢弃。"""
    parts = H1_RE.split(body)
    titles = parts[1::2]
    contents = parts[2::2]
    out: list[tuple[str, str]] = []
    for t, c in zip(titles, contents):
        title = t.strip()
        content = c.strip()
        if title and content:
            out.append((title, content))
    return out


def scan(root: Path) -> list[Path]:
    """枚举待 ingest 的 .md 文件。

    跳过：
      - ``_`` 开头的目录或文件
      - 顶层 ``README.md`` 和任意子目录下的 ``README.md``
    """
    out: list[Path] = []
    if not root.exists():
        return out
    for p in root.rglob("*.md"):
        rel = p.relative_to(root)
        if any(part.startswith("_") for part in rel.parts):
            continue
        if p.name.lower() == "readme.md":
            continue
        out.append(p)
    return sorted(out)


def parse_md(path: Path, root: Path) -> dict:
    """解析单个 .md → 中间结构。失败抛 ValueError。

    返回字段中 ``source_hash`` 为整文件 sha256，用于增量同步 diff。
    """
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)

    if "slug" not in meta or not str(meta.get("slug") or "").strip():
        raise ValueError("frontmatter 缺 slug")
    if "name" not in meta or not str(meta.get("name") or "").strip():
        raise ValueError("frontmatter 缺 name")

    rel = path.relative_to(root)
    inferred_subject = rel.parts[0] if len(rel.parts) > 1 else ""
    subject = str(meta.get("subject") or inferred_subject).strip()

    slug = str(meta["slug"]).strip()

    # 字符约束: subject / slug 不允许含 '/', 否则 cid 路径化会错位
    if not subject:
        raise ValueError(
            "无法推断 subject (请把 .md 放在子目录, 或在 frontmatter 里显式指定)"
        )
    if "/" in subject:
        raise ValueError(f"subject={subject!r} 不允许含有 '/'")
    if "/" in slug:
        raise ValueError(f"slug={slug!r} 不允许含有 '/'")

    aliases_raw = meta.get("aliases") or []
    if not isinstance(aliases_raw, list):
        raise ValueError("aliases 必须是列表")
    aliases: list[dict] = []
    for a in aliases_raw:
        if isinstance(a, str) and a.strip():
            aliases.append({"name": a.strip(), "lang": "zh"})
        elif isinstance(a, dict) and a.get("name"):
            aliases.append(
                {"name": str(a["name"]).strip(), "lang": str(a.get("lang") or "zh")}
            )

    tags_raw = meta.get("tags") or []
    if not isinstance(tags_raw, list):
        raise ValueError("tags 必须是列表")
    tags = [str(t).strip() for t in tags_raw if str(t).strip()]

    edges: dict[str, list[str]] = {}
    for fm_key, rel_type in REL_KEYS.items():
        targets = meta.get(fm_key) or []
        if not isinstance(targets, list):
            raise ValueError(f"{fm_key} 必须是列表")
        slugs = [str(t).strip() for t in targets if str(t).strip()]
        if slugs:
            edges[rel_type] = slugs

    try:
        difficulty = int(meta.get("difficulty", 3))
    except (TypeError, ValueError):
        difficulty = 3
    difficulty = max(0, min(5, difficulty))

    # H1 切段 + 同文件内 H1 唯一性校验 (负责 fid 唯一性)
    sections = split_h1(body)
    seen_kinds: dict[str, int] = {}
    for title, _content in sections:
        if "/" in title:
            raise ValueError(f"H1 标题={title!r} 不允许含有 '/'")
        seen_kinds[title] = seen_kinds.get(title, 0) + 1
    dup_kinds = [k for k, n in seen_kinds.items() if n > 1]
    if dup_kinds:
        raise ValueError(
            f"同一文件内 H1 标题重复: {dup_kinds} (请重命名使其唯一, 或合并到同一段)"
        )

    return {
        "slug": slug,
        "name": str(meta["name"]).strip(),
        "summary": str(meta.get("summary", "") or "").strip(),
        "subject": subject,
        "difficulty": difficulty,
        "aliases": aliases,
        "tags": tags,
        "sections": sections,
        "edges": edges,
        "source": str(rel),
        "source_hash": _file_hash(text),
    }


# ============================================================
# 全量重建（--rebuild 模式）
# ============================================================


def wipe_okf_data() -> dict[str, int]:
    """删除 KG 中所有 origin='okf' 的 facet/edge 与 created_by='okf' 的 concept。

    飞轮产出（dialog_aggregated / agent_authored）完全保留。
    返回各表删除行数。
    """
    with get_kg_db() as conn:
        n_e = conn.execute("DELETE FROM concept_edge WHERE origin='okf'").rowcount
        n_f = conn.execute("DELETE FROM facet WHERE origin='okf'").rowcount
        n_c = conn.execute("DELETE FROM concept WHERE created_by='okf'").rowcount
        conn.commit()
    return {"concept": int(n_c or 0), "facet": int(n_f or 0), "edge": int(n_e or 0)}


def _list_kg_okf_concept_ids() -> dict[str, str]:
    """读出 KG 中所有 created_by='okf' 的 concept: {cid: source_hash}。

    用于增量 diff，判断哪些 .md 被删了（在 KG 但不在 parsed 里）。
    """
    out: dict[str, str] = {}
    with get_kg_db() as conn:
        rows = conn.execute(
            "SELECT id, source_hash FROM concept WHERE created_by='okf'"
        ).fetchall()
    for r in rows:
        out[r["id"]] = r["source_hash"] or ""
    return out


# ============================================================
# 解析阶段：扫描 + parse + 校验
# ============================================================


class ParseResult:
    """parse 阶段的产物，给后面的 rebuild / incremental 共用。"""

    def __init__(
        self,
        parsed: list[dict],
        parse_errors: list[tuple[str, str]],
        cid_index: dict[tuple[str, str], str],
        slug_global_index: dict[str, list[str]],
    ) -> None:
        self.parsed = parsed
        self.parse_errors = parse_errors
        self.cid_index = cid_index  # (subject, slug) → cid
        self.slug_global_index = slug_global_index


def _parse_and_validate(root: Path) -> tuple[ParseResult, int]:
    """扫描+解析+全局校验。返回 (ParseResult, exit_code)；exit_code=0 表示通过。"""
    paths = scan(root)
    parsed: list[dict] = []
    parse_errors: list[tuple[str, str]] = []
    for p in paths:
        try:
            parsed.append(parse_md(p, root))
        except Exception as exc:  # pylint: disable=broad-except
            parse_errors.append((str(p.relative_to(root)), str(exc)))

    # 校验: (subject, slug) 全局唯一性
    seen: dict[tuple[str, str], str] = {}
    dup_errors: list[str] = []
    for d in parsed:
        key = (d["subject"], d["slug"])
        if key in seen:
            dup_errors.append(
                f"subject={d['subject']} slug={d['slug']}: {d['source']} vs {seen[key]}"
            )
        else:
            seen[key] = d["source"]
    if dup_errors:
        for e in dup_errors:
            print(f"❌ (subject, slug) 重复: {e}", file=sys.stderr)
        return ParseResult([], parse_errors, {}, {}), 2

    # 校验：关系类型合法
    rel_errors: list[str] = []
    for d in parsed:
        for rel in d["edges"]:
            if rel not in VALID_RELATION_TYPES:
                rel_errors.append(f"{d['source']}: 非法 relation_type={rel}")
    if rel_errors:
        for e in rel_errors:
            print(f"❌ {e}", file=sys.stderr)
        return ParseResult([], parse_errors, {}, {}), 3

    # 派生 cid + 建索引
    cid_index: dict[tuple[str, str], str] = {}
    slug_global_index: dict[str, list[str]] = {}
    for d in parsed:
        cid = derive_concept_id(d["subject"], d["slug"])
        cid_index[(d["subject"], d["slug"])] = cid
        slug_global_index.setdefault(d["slug"], []).append(cid)

    return ParseResult(parsed, parse_errors, cid_index, slug_global_index), 0


# ============================================================
# 关系解析（同学科默认 + 全名兜底）
# ============================================================


def _resolve_edge_target(
    src_subject: str,
    tgt_ref: str,
    cid_index: dict[tuple[str, str], str],
    slug_global_index: dict[str, list[str]],
) -> tuple[str | None, str | None, list[str]]:
    """把 frontmatter 关系字段里的引用解析成 dst_cid。

    返回 (dst_cid, error_kind, ambiguous_candidates)：
      - dst_cid 命中 → ("...", None, [])
      - 找不到       → (None, "dangling", [])
      - 歧义         → (None, "ambiguous", [候选 cid 列表])
    """
    if "/" in tgt_ref:
        sub, slg = tgt_ref.split("/", 1)
        dst = cid_index.get((sub.strip(), slg.strip()))
        return (dst, None, []) if dst else (None, "dangling", [])

    # 同学科优先
    dst = cid_index.get((src_subject, tgt_ref))
    if dst:
        return dst, None, []
    candidates = slug_global_index.get(tgt_ref, [])
    if len(candidates) == 1:
        return candidates[0], None, []
    if len(candidates) > 1:
        return None, "ambiguous", candidates
    return None, "dangling", []


# ============================================================
# 入库主流程
# ============================================================


def _write_concept_facets_and_edges_full(
    parsed: list[dict],
    cid_index: dict[tuple[str, str], str],
    slug_global_index: dict[str, list[str]],
) -> dict[str, Any]:
    """全量重建分支用：先删后写，所有 concept/facet/edge 都用 create。"""
    concept_repo = ConceptRepository()
    facet_repo = FacetRepository()
    edge_repo = ConceptEdgeRepository()

    concept_count = 0
    facet_count = 0
    edge_count = 0
    dangling: list[tuple[str, str, str]] = []
    selfloops: list[tuple[str, str]] = []
    ambiguous: list[tuple[str, str, str, list[str]]] = []

    # Pass 1: concept
    for d in parsed:
        cid = cid_index[(d["subject"], d["slug"])]
        concept_repo.create(
            ConceptCreate(
                id=cid,
                slug=d["slug"],
                canonical_name=d["name"],
                summary=d["summary"],
                subject=d["subject"],
                difficulty=d["difficulty"],
                aliases=[ConceptAlias(**a) for a in d["aliases"]],
                tags=d["tags"],
                status="approved",
                source_hash=d["source_hash"],
                created_by="okf",
            )
        )
        concept_count += 1

    # Pass 2: facet
    for d in parsed:
        cid = cid_index[(d["subject"], d["slug"])]
        brief = concept_repo.get_by_id(cid)
        for title, content in d["sections"]:
            try:
                facet_repo.create(
                    FacetCreate(
                        id=derive_facet_id(cid, title),
                        concept_id=cid,
                        kind=title,
                        content=content,
                        origin="okf",
                        origin_ref={"source": d["source"]},
                        status="active",
                        confidence=1.0,
                        created_by="okf",
                    ),
                    concept_brief=brief,
                )
                facet_count += 1
            except Exception:  # pylint: disable=broad-except
                logger.exception("facet 写入失败 slug=%s kind=%s", d["slug"], title)

    # Pass 3: edge
    for d in parsed:
        src_cid = cid_index[(d["subject"], d["slug"])]
        for rel, targets in d["edges"].items():
            for tgt_ref in targets:
                dst_cid, err, cands = _resolve_edge_target(
                    d["subject"], tgt_ref, cid_index, slug_global_index
                )
                if err == "ambiguous":
                    ambiguous.append((d["slug"], rel, tgt_ref, cands))
                    continue
                if not dst_cid:
                    dangling.append((d["slug"], rel, tgt_ref))
                    continue
                if src_cid == dst_cid:
                    selfloops.append((d["slug"], rel))
                    continue
                try:
                    edge_repo.create(
                        ConceptEdgeCreate(
                            id=derive_edge_id(src_cid, dst_cid, rel),
                            src_id=src_cid,
                            dst_id=dst_cid,
                            relation_type=rel,
                            weight=1.0,
                            status="approved",
                            origin="okf",
                            origin_ref={"source": d["source"]},
                            created_by="okf",
                        )
                    )
                    edge_count += 1
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning(
                        "edge 写入失败 %s -[%s]-> %s: %s", d["slug"], rel, tgt_ref, exc
                    )

    return {
        "concept": {
            "created": concept_count,
            "updated": 0,
            "unchanged": 0,
            "deleted": 0,
        },
        "facet": {"created": facet_count, "updated": 0, "unchanged": 0, "deleted": 0},
        "edge": {"created": edge_count, "unchanged": 0, "deleted": 0},
        "dangling": dangling,
        "selfloops": selfloops,
        "ambiguous": ambiguous,
    }


def _sync_incremental(
    parsed: list[dict],
    cid_index: dict[tuple[str, str], str],
    slug_global_index: dict[str, list[str]],
) -> dict[str, Any]:
    """增量同步：基于 concept.source_hash 做 diff。"""
    concept_repo = ConceptRepository()
    facet_repo = FacetRepository()
    edge_repo = ConceptEdgeRepository()

    # KG 现状：所有 OKF concept 的 cid → source_hash
    kg_okf = _list_kg_okf_concept_ids()
    parsed_cids = {cid_index[(d["subject"], d["slug"])] for d in parsed}

    # 计数器
    c_stats = {"created": 0, "updated": 0, "unchanged": 0, "deleted": 0}
    f_stats = {"created": 0, "updated": 0, "unchanged": 0, "deleted": 0}
    e_stats = {"created": 0, "unchanged": 0, "deleted": 0}
    dangling: list[tuple[str, str, str]] = []
    selfloops: list[tuple[str, str]] = []
    ambiguous: list[tuple[str, str, str, list[str]]] = []

    # ---------- Phase A: 先删 .md 已下线的 concept ----------
    to_delete = [cid for cid in kg_okf if cid not in parsed_cids]
    for cid in to_delete:
        # 先删该 concept 名下 OKF facet（CASCADE 也会删，但向量库要单独清）
        for f in facet_repo.list_by_concept_and_origin(cid, origin="okf"):
            facet_repo.delete(f.id)
            f_stats["deleted"] += 1
        # 再删该 concept 出向 OKF edge（注意 src=cid 的；dst=cid 的稍后会被对侧删除自然解开）
        for e in edge_repo.list_by_origin_and_src(cid, origin="okf"):
            edge_repo.delete(e.id)
            e_stats["deleted"] += 1
        # 同时显式删入向 OKF edge（避免外键 RESTRICT 阻塞 concept 删除）
        with get_kg_db() as conn:
            rows = conn.execute(
                "SELECT id FROM concept_edge WHERE dst_id=? AND origin='okf'",
                (cid,),
            ).fetchall()
        for r in rows:
            edge_repo.delete(r["id"])
            e_stats["deleted"] += 1
        # 最后删 concept 自身
        if concept_repo.delete(cid):
            c_stats["deleted"] += 1

    # ---------- Phase B: concept upsert ----------
    # 保存每个 cid 是 created/updated/unchanged，决定是否要做 facet/edge diff
    cid_action: dict[str, str] = {}
    for d in parsed:
        cid = cid_index[(d["subject"], d["slug"])]
        _, action = concept_repo.upsert(
            ConceptCreate(
                id=cid,
                slug=d["slug"],
                canonical_name=d["name"],
                summary=d["summary"],
                subject=d["subject"],
                difficulty=d["difficulty"],
                aliases=[ConceptAlias(**a) for a in d["aliases"]],
                tags=d["tags"],
                status="approved",
                source_hash=d["source_hash"],
                created_by="okf",
            )
        )
        c_stats[action] += 1
        cid_action[cid] = action

    # ---------- Phase C: facet diff（仅对 created / updated 的 concept 做）----------
    for d in parsed:
        cid = cid_index[(d["subject"], d["slug"])]
        action = cid_action[cid]
        if action == "unchanged":
            # 文件 sha256 没变：facet 也一定没变，整文件跳过
            n = sum(1 for _ in d["sections"])
            f_stats["unchanged"] += n
            continue

        brief = concept_repo.get_by_id(cid)

        # 期望集合（从解析结果）
        expected_fids = {
            derive_facet_id(cid, title): (title, content)
            for title, content in d["sections"]
        }
        # 现状集合（从 KG）
        existing = {
            f.id: f for f in facet_repo.list_by_concept_and_origin(cid, origin="okf")
        }

        # 删除：现状有但期望没有的
        for fid in set(existing) - set(expected_fids):
            if facet_repo.delete(fid):
                f_stats["deleted"] += 1

        # 创建/更新：期望中的逐条 upsert
        for fid, (title, content) in expected_fids.items():
            try:
                _, sub_action = facet_repo.upsert(
                    FacetCreate(
                        id=fid,
                        concept_id=cid,
                        kind=title,
                        content=content,
                        origin="okf",
                        origin_ref={"source": d["source"]},
                        status="active",
                        confidence=1.0,
                        created_by="okf",
                    ),
                    concept_brief=brief,
                )
                f_stats[sub_action] += 1
            except Exception:  # pylint: disable=broad-except
                logger.exception("facet upsert 失败 cid=%s kind=%s", cid, title)

    # ---------- Phase D: edge diff（仅对 created / updated 的 concept 做）----------
    for d in parsed:
        src_cid = cid_index[(d["subject"], d["slug"])]
        action = cid_action[src_cid]
        if action == "unchanged":
            # 文件没变 → 边一定没变，整文件跳过
            n = sum(len(v) for v in d["edges"].values())
            e_stats["unchanged"] += n
            continue

        # 期望边集合：dict[eid] = (dst_cid, rel)
        expected_eids: dict[str, tuple[str, str]] = {}
        for rel, targets in d["edges"].items():
            for tgt_ref in targets:
                dst_cid, err, cands = _resolve_edge_target(
                    d["subject"], tgt_ref, cid_index, slug_global_index
                )
                if err == "ambiguous":
                    ambiguous.append((d["slug"], rel, tgt_ref, cands))
                    continue
                if not dst_cid:
                    dangling.append((d["slug"], rel, tgt_ref))
                    continue
                if src_cid == dst_cid:
                    selfloops.append((d["slug"], rel))
                    continue
                expected_eids[derive_edge_id(src_cid, dst_cid, rel)] = (dst_cid, rel)

        # 现状边集合
        existing_edges = {
            e.id: e for e in edge_repo.list_by_origin_and_src(src_cid, origin="okf")
        }

        # 删：现状有但期望没有
        for eid in set(existing_edges) - set(expected_eids):
            if edge_repo.delete(eid):
                e_stats["deleted"] += 1

        # 写：期望中的逐条 upsert
        for eid, (dst_cid, rel) in expected_eids.items():
            try:
                _, sub_action = edge_repo.upsert(
                    ConceptEdgeCreate(
                        id=eid,
                        src_id=src_cid,
                        dst_id=dst_cid,
                        relation_type=rel,
                        weight=1.0,
                        status="approved",
                        origin="okf",
                        origin_ref={"source": d["source"]},
                        created_by="okf",
                    )
                )
                e_stats[sub_action] += 1
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "edge upsert 失败 %s -[%s]-> %s: %s", d["slug"], rel, dst_cid, exc
                )

    return {
        "concept": c_stats,
        "facet": f_stats,
        "edge": e_stats,
        "dangling": dangling,
        "selfloops": selfloops,
        "ambiguous": ambiguous,
    }


# ============================================================
# 顶层 ingest 入口
# ============================================================


def ingest(root: Path, dry_run: bool = False, rebuild: bool = False) -> int:
    """主流程。返回退出码（0=成功）。

    Args:
        root: OKF Bundle 根目录。
        dry_run: True 时仅打印计划，不写 DB。
        rebuild: True 时走"全量删 + 全量建"（早期开发常用）；
                 False（默认）走"基于 source_hash 的 diff 增量同步"。
    """
    if not root.exists():
        print(f"❌ 路径不存在: {root}", file=sys.stderr)
        return 1

    init_kg_db()  # 幂等：保证表结构存在

    parse_result, code = _parse_and_validate(root)
    if code != 0:
        return code
    parsed = parse_result.parsed
    parse_errors = parse_result.parse_errors

    # ----- dry-run 提前返回 -----
    if dry_run:
        kg_okf = _list_kg_okf_concept_ids()
        parsed_cids = {
            parse_result.cid_index[(d["subject"], d["slug"])] for d in parsed
        }
        n_to_add = len(parsed_cids - set(kg_okf))
        n_to_check = len(parsed_cids & set(kg_okf))
        n_to_delete = len(set(kg_okf) - parsed_cids)
        n_unchanged = sum(
            1
            for d in parsed
            if (cid := parse_result.cid_index[(d["subject"], d["slug"])]) in kg_okf
            and kg_okf[cid] == d["source_hash"]
        )
        print(f"[DRY] 共 {len(parsed)} 个 concept (.md):")
        print(f"  + 新增: {n_to_add}")
        print(f"  ~ 待检查: {n_to_check}  (其中 hash 未变跳过: {n_unchanged})")
        print(f"  - 删除: {n_to_delete}")
        print()
        for d in parsed:
            cid = parse_result.cid_index[(d["subject"], d["slug"])]
            if cid not in kg_okf:
                tag = "+ NEW"
            elif kg_okf[cid] == d["source_hash"]:
                tag = "= SAME"
            else:
                tag = "~ DIFF"
            n_edges = sum(len(v) for v in d["edges"].values())
            print(
                f"  {tag}  {cid:30s}  facets={len(d['sections']):2d}  "
                f"edges={n_edges:2d}  ({d['source']})"
            )
        if parse_errors:
            print(f"\n[DRY] {len(parse_errors)} 个 .md 解析失败:")
            for src, err in parse_errors:
                print(f"  ! {src}: {err}")
        if rebuild:
            print("\n[DRY] --rebuild 模式：实际执行时会先 wipe 所有 OKF 数据再重建。")
        else:
            print("\n[DRY] 默认增量模式：未实际写入 DB。")
        return 0

    # ----- 真正写库 -----
    if rebuild:
        wipe_stats = wipe_okf_data()
        print(
            f"🧹 [rebuild] wiped okf: concept={wipe_stats['concept']}, "
            f"facet={wipe_stats['facet']}, edge={wipe_stats['edge']}"
        )
        report = _write_concept_facets_and_edges_full(
            parsed, parse_result.cid_index, parse_result.slug_global_index
        )
        mode_label = "rebuild"
    else:
        report = _sync_incremental(
            parsed, parse_result.cid_index, parse_result.slug_global_index
        )
        mode_label = "incremental"

    # ----- 报告 -----
    c = report["concept"]
    f = report["facet"]
    e = report["edge"]
    print(f"\n✅ ingest done ({mode_label})")
    print(
        f"   concepts:  +{c['created']} added, ~{c['updated']} updated, "
        f"-{c['deleted']} deleted, {c['unchanged']} unchanged"
    )
    print(
        f"   facets:    +{f['created']} added, ~{f['updated']} updated, "
        f"-{f['deleted']} deleted, {f['unchanged']} unchanged"
    )
    print(
        f"   edges:     +{e['created']} added, "
        f"-{e['deleted']} deleted, {e['unchanged']} unchanged"
    )
    if parse_errors:
        print(f"   ⚠️  parse errors: {len(parse_errors)}")
        for src, err in parse_errors:
            print(f"      {src}: {err}")
    if report["dangling"]:
        print(f"   ⚠️  dangling links: {len(report['dangling'])}")
        for src, rel, tgt in report["dangling"]:
            print(f"      {src} -[{rel}]-> {tgt}  (slug 未找到)")
    if report["ambiguous"]:
        print(f"   ⚠️  ambiguous links: {len(report['ambiguous'])}")
        for src, rel, tgt, cands in report["ambiguous"]:
            print(
                f"      {src} -[{rel}]-> {tgt}  歧义后选: {cands} "
                f"(请改写为 'subject/slug' 全名)"
            )
    if report["selfloops"]:
        print(f"   ⚠️  self-loops skipped: {len(report['selfloops'])}")
        for src, rel in report["selfloops"]:
            print(f"      {src} -[{rel}]-> {src}")

    return 0


# ============================================================
# CLI
# ============================================================


def _parse_args(argv: list[str] | None = None) -> Any:
    ap = argparse.ArgumentParser(
        description="OKF Bundle → KG 同步器（默认增量；--rebuild 全量重建）"
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=Path("knowledge"),
        help="OKF Bundle 根目录（默认 knowledge/）",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印计划，不写 DB",
    )
    ap.add_argument(
        "--rebuild",
        action="store_true",
        help="全量重建：先删所有 origin='okf' 数据再重建（早期开发常用）",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _parse_args(argv)
    return ingest(args.root, dry_run=args.dry_run, rebuild=args.rebuild)


if __name__ == "__main__":
    sys.exit(main())
