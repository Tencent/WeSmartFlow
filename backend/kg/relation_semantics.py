"""
关系语义嵌入模块

核心思想：
  把"图上的边类型"和"内容类型（展示 vs 证据）"也看作可被 embedding 的语义。
  query 来了之后，用同一个 embedder 把 query 向量化，再与各类语义 probe 的均值向量
  做余弦相似度，得到一张连续的"权重表"，驱动 Graph RAG 的扩展和内容选取。

为什么这么做：
  - 复用 query embedding（Stage 1 已经算过），增量成本几乎为 0
  - 输出连续权重，比离散意图分类更细腻、天然支持复合意图
  - 易扩展：加新关系只要写一段 probe，无需训练
  - 全链路只用一个核心算子：余弦相似度

probe 设计原则：
  - 每个语义类型给 4~6 句"用户可能怎么问"
  - 用学生口语 + 一点数学术语，不要写抽象定义
  - 多角度覆盖（动机/操作/对比/疑问），降低单句偏置
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache

from .embedder import get_embedder

logger = logging.getLogger(__name__)


# ============================================================
# 关系类型 probe
# ============================================================
# 注：覆盖 models.VALID_RELATION_TYPES 中定义的全部关系类型
# 设计 query 时刻意写"学生口吻"，避免学术化句子带偏 embedding。
# ============================================================

RELATION_PROBES: dict[str, list[str]] = {
    "prerequisite": [
        "学这个之前需要先掌握什么",
        "这个概念依赖哪些基础知识",
        "前置知识有哪些",
        "学之前要会什么",
        "需要先学会哪些内容",
    ],
    "part_of": [
        "这个是哪一章的内容",
        "属于哪个大主题",
        "整体框架里它在哪个位置",
        "它是更大概念的一部分吗",
    ],
    "related": [
        "和这个相关的概念有哪些",
        "顺带可以了解什么",
        "周边知识点",
        "类似话题",
    ],
    "contrasts": [
        "这两个有什么区别",
        "对比一下",
        "容易混淆的概念",
        "和它相反的是什么",
        "区别和联系",
    ],
    "application_of": [
        "怎么用这个解题",
        "实际应用是什么",
        "怎么用在实际问题里",
        "举个应用例子",
        "用在哪里",
    ],
    "special_case_of": [
        "这是不是某个更一般概念的特殊情况",
        "特例",
        "更一般的形式是什么",
    ],
    "generalizes": [
        "这个能推广到什么",
        "更一般的版本",
        "推广形式",
        "扩展形式",
    ],
    "equivalent_to": [
        "这两个是不是等价的",
        "另一种说法",
        "同义概念",
        "另一种表达",
    ],
}


# ============================================================
# 内容类型 probe（展示 vs 证据）
# ============================================================
# 在我们的 schema 里：
#   exhibit (markdown_note/quiz/viz/card/...) = 展示型（讲解、直觉、例子）
#   chunk   (来自 textbook/paper/article)      = 证据型（严谨表述、推导、出处）
# ============================================================

CONTENT_PROBES: dict[str, list[str]] = {
    "display": [
        "通俗讲解一下",
        "直观理解",
        "举个例子",
        "怎么操作",
        "给我讲讲",
        "怎么用",
        "是什么意思",
    ],
    "evidence": [
        "严格定义是什么",
        "为什么成立",
        "怎么证明",
        "定理表述",
        "课本上怎么说",
        "原文",
        "理论依据",
        "推导过程",
    ],
}


# ============================================================
# 内部工具
# ============================================================


def _cos(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _mean_vec(vecs: list[list[float]]) -> list[float]:
    """求一组向量的逐元素平均，跳过空向量。"""
    valid = [v for v in vecs if v]
    if not valid:
        return []
    dim = len(valid[0])
    out = [0.0] * dim
    for v in valid:
        for i, x in enumerate(v):
            out[i] += x
    n = float(len(valid))
    return [x / n for x in out]


# ============================================================
# 单例：离线一次性计算 probe 均值向量
# ============================================================


class _SemanticProbes:
    """离线建表：每个类型 → 多条 probe 的均值 embedding。"""

    def __init__(self) -> None:
        self.relation_emb: dict[str, list[float]] = {}
        self.content_emb: dict[str, list[float]] = {}
        self.enabled: bool = False
        self._build()

    def _build(self) -> None:
        embedder = get_embedder()
        if not embedder or getattr(embedder, "dim", 0) <= 0:
            logger.info("relation_semantics: embedder 未启用，关系语义打分关闭")
            self.enabled = False
            return

        # 一次性把所有 probe 文本批量送进 embedder，省 API 调用
        flat_texts: list[str] = []
        index_map: list[tuple[str, str]] = []  # [(category, key)]，每条 probe 对应

        for rel, probes in RELATION_PROBES.items():
            for p in probes:
                flat_texts.append(p)
                index_map.append(("relation", rel))

        for ct, probes in CONTENT_PROBES.items():
            for p in probes:
                flat_texts.append(p)
                index_map.append(("content", ct))

        try:
            vecs = embedder.embed_many(flat_texts)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("relation_semantics: probe 嵌入失败 err=%s", exc)
            self.enabled = False
            return

        # 按 (category, key) 聚合
        bucket: dict[tuple[str, str], list[list[float]]] = {}
        for (cat, key), v in zip(index_map, vecs):
            bucket.setdefault((cat, key), []).append(v)

        for (cat, key), vs in bucket.items():
            mean = _mean_vec(vs)
            if not mean:
                continue
            if cat == "relation":
                self.relation_emb[key] = mean
            else:
                self.content_emb[key] = mean

        self.enabled = bool(self.relation_emb and self.content_emb)
        if self.enabled:
            logger.info(
                "relation_semantics: 已加载 %d 种关系 probe + %d 种内容 probe",
                len(self.relation_emb),
                len(self.content_emb),
            )


@lru_cache(maxsize=1)
def get_probes() -> _SemanticProbes:
    return _SemanticProbes()


def reload_probes() -> _SemanticProbes:
    """清空 probe 缓存并强制重新构建。

    什么时候调:
      - 切换 embedder 模型/维度后(env 改了,但进程没重启)
      - reindex 脚本在 vec_store DROP 重建后,probe 也需要重新 embed
      - 单元测试要在不重启进程的情况下重置状态

    这里直接清 lru_cache,下次 get_probes() 会触发重新 embed。
    """
    get_probes.cache_clear()
    return get_probes()


# ============================================================
# 对外打分 API
# ============================================================


def score_relations(query_emb: list[float]) -> dict[str, float]:
    """对 query 给出每种关系类型的余弦相似度。
    返回值范围 [-1, 1]，未启用时返回空 dict。
    """
    probes = get_probes()
    if not probes.enabled or not query_emb:
        return {}
    return {rel: _cos(query_emb, vec) for rel, vec in probes.relation_emb.items()}


def score_content_types(query_emb: list[float]) -> dict[str, float]:
    """对 query 给出每种内容类型的余弦相似度。
    返回 {'display': float, 'evidence': float}；未启用时返回空 dict。
    """
    probes = get_probes()
    if not probes.enabled or not query_emb:
        return {}
    return {ct: _cos(query_emb, vec) for ct, vec in probes.content_emb.items()}


def softmax_normalize(
    scores: dict[str, float], temperature: float = 0.1
) -> dict[str, float]:
    """把余弦相似度（差距通常很小）归一化为概率分布。
    温度越低，分布越尖锐——更倾向于挑出最相关的关系/内容类型。
    """
    if not scores:
        return {}
    max_s = max(scores.values())
    exps = {
        k: math.exp((v - max_s) / max(1e-6, temperature)) for k, v in scores.items()
    }
    z = sum(exps.values()) or 1.0
    return {k: v / z for k, v in exps.items()}
