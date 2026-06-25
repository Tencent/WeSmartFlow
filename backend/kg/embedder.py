"""
KG 嵌入服务

设计要点：
- 单一抽象 `Embedder`，通过环境变量决定具体实现
- `NullEmbedder` 占位：未配置 KG_EMBEDDING_API_KEY 时使用，向量通道关闭
- `OpenAICompatEmbedder`：兼容 OpenAI / 阿里百炼 / 任何 OpenAI 风格 embeddings 接口

环境变量：
  KG_EMBEDDING_API_KEY    必需，留空则关闭向量通道
  KG_EMBEDDING_BASE_URL   兼容接口的 base url（如百炼 https://dashscope.aliyuncs.com/compatible-mode/v1）
  KG_EMBEDDING_MODEL      模型名（默认 text-embedding-v4）
  KG_EMBEDDING_DIM        向量维度（默认 1024）
  KG_EMBEDDING_BATCH      单次请求最多条数（默认 10，迁就百炼上限）
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

from .config import (
    KG_EMBEDDING_API_KEY,
    KG_EMBEDDING_BASE_URL,
    KG_EMBEDDING_BATCH,
    KG_EMBEDDING_DIM,
    KG_EMBEDDING_MODEL,
)

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """嵌入器协议。"""

    dim: int
    model: str

    def embed_one(self, text: str) -> list[float]: ...

    def embed_many(self, texts: list[str]) -> list[list[float]]: ...


class NullEmbedder:
    """占位实现：所有方法返回空向量；vector_store 检测到 dim==0 后关闭向量通道。"""

    dim: int = 0
    model: str = ""

    def embed_one(self, text: str) -> list[float]:
        return []

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


class OpenAICompatEmbedder:
    """OpenAI 兼容 embedding 客户端（OpenAI / 阿里百炼 / 任意兼容服务）。"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        dim: int,
        batch_size: int = 10,
    ) -> None:
        # 延迟导入，避免没装 openai 的环境直接 import 失败
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url or None)
        self.model = model
        self.dim = dim
        self.batch_size = max(1, batch_size)

    def _call(self, inp) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self.model, input=inp)
        return [d.embedding for d in resp.data]

    def embed_one(self, text: str) -> list[float]:
        if not text:
            return []
        out = self._call(text)
        return out[0] if out else []

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result: list[list[float]] = []
        # 跳过空串但占位返回 []，方便上游对齐 index
        cleaned: list[tuple[int, str]] = [(i, t) for i, t in enumerate(texts) if t]
        out_map: dict[int, list[float]] = {}
        for batch_start in range(0, len(cleaned), self.batch_size):
            batch = cleaned[batch_start : batch_start + self.batch_size]
            inputs = [t for _, t in batch]
            vecs = self._call(inputs)
            for (idx, _), vec in zip(batch, vecs):
                out_map[idx] = vec
        for i in range(len(texts)):
            result.append(out_map.get(i, []))
        return result


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """根据 config 返回单例 Embedder。"""
    if not KG_EMBEDDING_API_KEY:
        logger.info("KG embedder: KG_EMBEDDING_API_KEY 未配置，向量通道关闭")
        return NullEmbedder()

    try:
        emb = OpenAICompatEmbedder(
            api_key=KG_EMBEDDING_API_KEY,
            base_url=KG_EMBEDDING_BASE_URL,
            model=KG_EMBEDDING_MODEL,
            dim=KG_EMBEDDING_DIM,
            batch_size=KG_EMBEDDING_BATCH,
        )
        logger.info(
            "KG embedder: 已启用 OpenAI 兼容客户端 model=%s dim=%d",
            KG_EMBEDDING_MODEL,
            KG_EMBEDDING_DIM,
        )
        return emb
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("KG embedder: 初始化失败，回退为 NullEmbedder：%s", exc)
        return NullEmbedder()
