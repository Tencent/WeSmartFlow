"""
KG 子模块配置

通过环境变量驱动（统一放在仓库根 .env，模板见 backend/.env.example）：
- KG_DATA_DIR：数据根目录（默认仓库根 ./data）
- KG_DB_FILE：SQLite 文件名（默认 kg.db）
- KG_VEC_DB_FILE：向量库 SQLite 文件名（默认 kg_vec.db，基于 sqlite-vec）
- KG_EMBEDDING_API_KEY / KG_EMBEDDING_BASE_URL / KG_EMBEDDING_MODEL / KG_EMBEDDING_DIM

启动时加载仓库根 .env（backend 进程一般已加载过；这里提供补充入口，
让脚本（seed/reindex/bench）也能跳过 backend 独立运行）。
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # 不依赖也能跑（环境变量直接设置即可）

    def load_dotenv(*_args, **_kwargs) -> None:  # type: ignore[misc]
        return None


# ---- .env 加载（仓库根，单一来源） ----
# kg 位于 backend/kg/，所以 _PKG_DIR.parent 是 backend/，再往上才是仓库根
_PKG_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _PKG_DIR.parent
_REPO_ROOT = _BACKEND_DIR.parent

_root_env = _REPO_ROOT / ".env"
if _root_env.exists():
    load_dotenv(_root_env, override=False)

# ---- 数据目录 ----
DATA_DIR = (
    Path(os.getenv("KG_DATA_DIR") or str(_REPO_ROOT / "data")).expanduser().resolve()
)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---- 数据库 ----
KG_DB_FILE = os.getenv("KG_DB_FILE", "kg.db")
KG_DB_PATH = DATA_DIR / KG_DB_FILE

# ---- 向量存储（sqlite-vec，单文件，多进程友好） ----
KG_VEC_DB_FILE = os.getenv("KG_VEC_DB_FILE", "kg_vec.db")
KG_VEC_DB_PATH = os.getenv("KG_VEC_DB_PATH", "").strip() or str(
    DATA_DIR / KG_VEC_DB_FILE
)

# ---- Embedder ----
KG_EMBEDDING_API_KEY = os.getenv("KG_EMBEDDING_API_KEY", "").strip()
KG_EMBEDDING_BASE_URL = os.getenv("KG_EMBEDDING_BASE_URL", "").strip()
KG_EMBEDDING_MODEL = os.getenv("KG_EMBEDDING_MODEL", "text-embedding-v4").strip()
try:
    KG_EMBEDDING_DIM = int(os.getenv("KG_EMBEDDING_DIM", "1024"))
except ValueError:
    KG_EMBEDDING_DIM = 1024
try:
    KG_EMBEDDING_BATCH = int(os.getenv("KG_EMBEDDING_BATCH", "10"))
except ValueError:
    KG_EMBEDDING_BATCH = 10


# ---- Retrieve / Graph RAG 调参 ----
def _f(env: str, default: float) -> float:
    try:
        return float(os.getenv(env, str(default)))
    except ValueError:
        return default


def _i(env: str, default: int) -> int:
    try:
        return int(os.getenv(env, str(default)))
    except ValueError:
        return default


# 入口锚定（_anchor）
KG_ANCHOR_TOPK = _i("KG_ANCHOR_TOPK", 8)
KG_ANCHOR_MIN_SCORE = _f("KG_ANCHOR_MIN_SCORE", 0.55)
KG_ANCHOR_GAP_RATIO = _f("KG_ANCHOR_GAP_RATIO", 0.85)
KG_ANCHOR_MAX_ENTRIES = _i("KG_ANCHOR_MAX_ENTRIES", 3)
# 介于 [WEAK, MIN) 的候选会进入 weak_candidates，不参与扩展
KG_ANCHOR_WEAK_SCORE = _f("KG_ANCHOR_WEAK_SCORE", 0.40)

# 子图扩展（_expand_subgraph）
KG_REL_WEIGHT_FLOOR = _f("KG_REL_WEIGHT_FLOOR", 0.30)
KG_NEIGHBOR_FANOUT = _i("KG_NEIGHBOR_FANOUT", 12)


# ---- Chat 接入 / 自动闭环 ----

# 入口前置 RAG（在 chat 调 LLM 前自动检索一次 KG 注入 system prompt）
KG_CHAT_PRERAG_ENABLED = os.getenv("KG_CHAT_PRERAG_ENABLED", "1").strip() != "0"
KG_CHAT_PRERAG_TIMEOUT_MS = _i("KG_CHAT_PRERAG_TIMEOUT_MS", 800)
KG_CHAT_PRERAG_TOP_CONCEPTS = _i("KG_CHAT_PRERAG_TOP_CONCEPTS", 3)
KG_CHAT_PRERAG_TOP_FACETS_PER_CONCEPT = _i("KG_CHAT_PRERAG_TOP_FACETS_PER_CONCEPT", 3)

# ---- 后台聚合器周期 ----
# 后台聚合器周期（秒）
KG_AGGREGATOR_PERIOD_SEC = _i("KG_AGGREGATOR_PERIOD_SEC", 300)
KG_AGGREGATOR_BATCH_SIZE = _i("KG_AGGREGATOR_BATCH_SIZE", 200)

# ---- 向量双写一致性 ----
# True：concept/facet 的向量同步失败时自动回滚 SQLite，保证两边一致；
# False（默认）：向量软失败（不抛/不回滚），由后续对账 job 重 reindex。
# 生产建议 True；本地无 embedder/向量库时保持 False，否则任何写入都会失败。
KG_STRICT_VECTOR_WRITE = os.getenv("KG_STRICT_VECTOR_WRITE", "0").strip() == "1"
