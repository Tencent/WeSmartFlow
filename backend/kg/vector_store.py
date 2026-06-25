"""
KG 向量存储（sqlite-vec）

为什么换：
  - Qdrant 嵌入式模式独占文件锁，旁路脚本无法访问；服务模式又要起额外进程。
  - 我们这边场景只用到 "带 ANN 的 KV 存储 + payload"，sqlite-vec 一对一覆盖，
    且基于 SQLite WAL 天然支持多进程并发读 + 单进程写。

数据布局：
  单个 SQLite 文件 KG_VEC_DB_PATH（默认 data/kg_vec.db）下：

  - vec_concept(rowid, embedding float[D])   ← vec0 虚表（存向量）
  - vec_facet(rowid,   embedding float[D])   ← vec0 虚表（存向量）
  - vec_meta(collection TEXT, rowid INTEGER, biz_id TEXT, payload TEXT)
        ← 普通表，存业务 id ↔ rowid 映射 + payload(JSON)
        ← (collection, biz_id) UNIQUE，便于 upsert
        ← rowid 由我们自行分配（biz_id 的 64 位 hash），保证同一 biz_id 重复 upsert 落到同一行

embedder.dim == 0 时，所有方法变成 no-op，行为与旧版完全一致。

公开 API 完全保持兼容：
  - COLLECTION_CONCEPT / COLLECTION_FACET / ALL_COLLECTIONS
  - VectorStore.upsert(collection, biz_id, text, payload) -> (vector_id, model)
  - VectorStore.upsert_many(collection, items) -> [(vector_id, model), ...]
  - VectorStore.search(collection, query_text, top_k=10, concept_ids=None)
        -> [{biz_id, score, payload}]
  - VectorStore.delete(collection, biz_id)
  - VectorStore.delete_many(collection, biz_ids)
  - VectorStore.close()
  - get_vector_store()
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import struct
import threading
from pathlib import Path
from typing import Optional

from .config import KG_VEC_DB_PATH
from .embedder import Embedder, get_embedder

logger = logging.getLogger(__name__)

COLLECTION_CONCEPT = "kg_concept"
COLLECTION_FACET = "kg_facet"
ALL_COLLECTIONS = [COLLECTION_CONCEPT, COLLECTION_FACET]

# vec 表名对照
_VEC_TABLE = {
    COLLECTION_CONCEPT: "vec_concept",
    COLLECTION_FACET: "vec_facet",
}


# rowid 命名空间偏移：concept 与 facet 共享一个 vec_meta，
# 但各自有独立的 vec_xxx 虚表，所以 rowid 只在自己虚表里保证唯一即可。
# 这里用 collection 做 hash salt，避免不同 collection 的 biz_id 偶尔撞 rowid 之后混淆。
def _biz_to_rowid(collection: str, biz_id: str) -> int:
    """biz_id → 稳定的 64 位正整数 rowid（用作 vec0 虚表主键）。

    SQLite rowid 是有符号 64 位，我们截 63 位保证非负。
    sha1 碰撞概率在 2^63 量级几乎为 0，concept/facet 各自最多几万条，
    生日攻击概率可忽略。
    """
    h = hashlib.sha1(f"{collection}:{biz_id}".encode("utf-8")).digest()
    n = int.from_bytes(h[:8], "big", signed=False) & ((1 << 63) - 1)
    return n or 1  # 0 不能用作 rowid


def _vec_to_blob(vec: list[float]) -> bytes:
    """float32 序列 → sqlite-vec 期望的 little-endian 紧凑字节串。"""
    return struct.pack(f"{len(vec)}f", *vec)


class VectorStore:
    """sqlite-vec 单文件向量存储。"""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self.enabled = bool(embedder and embedder.dim > 0)
        self._conn: Optional[sqlite3.Connection] = None
        # SQLite Connection 不支持跨线程共享（默认 check_same_thread=True），
        # 我们这里允许多线程使用同一个连接，但用一把锁串行化写。
        # 读路径同样走锁（短临界区），简单可靠。
        self._lock = threading.Lock()
        if not self.enabled:
            logger.info("KG VectorStore: embedder 未启用，向量通道关闭")
            return
        self._init_db()

    # ---------------- 初始化 ----------------

    def _init_db(self) -> None:
        try:
            import sqlite_vec  # noqa: F401  仅探测可用性
        except ImportError:
            logger.warning(
                "KG VectorStore: 未安装 sqlite-vec，向量通道关闭。"
                "请执行：pip install sqlite-vec"
            )
            self.enabled = False
            return

        try:
            db_path = Path(KG_VEC_DB_PATH)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            # check_same_thread=False：我们用 self._lock 自己保证串行
            conn = sqlite3.connect(
                str(db_path), check_same_thread=False, isolation_level=None
            )
            conn.row_factory = sqlite3.Row

            # 加载 sqlite-vec 扩展
            conn.enable_load_extension(True)
            import sqlite_vec as _sv

            _sv.load(conn)
            conn.enable_load_extension(False)

            # 写入更友好的 PRAGMA：WAL 多读单写，外加 NORMAL 同步
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA busy_timeout=5000")

            self._conn = conn
            self._ensure_schema()
            logger.info(
                "KG VectorStore: sqlite-vec 已就绪 path=%s dim=%d",
                db_path,
                self.embedder.dim,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("KG VectorStore: sqlite-vec 初始化失败 err=%s", exc)
            self.enabled = False
            self._conn = None

    def _ensure_schema(self) -> None:
        """幂等建表：两张 vec0 虚表 + 一张 meta 普通表。

        vec0 虚表的 dim 与 distance_metric 在 CREATE 时定死，无法 ALTER。
        所以这里做"指纹比对"：把当前 embedder 期望的 (dim, metric) 与 sqlite_master
        里已有的建表 SQL 对一遍，发现不一致就 DROP 重建。
        重建后向量数据丢失，但业务侧只要重新跑一遍 upsert 即可恢复——这比让
        老 schema(默认 L2 距离 / 旧维度) 继续返回错误的相似度安全得多。
        """
        assert self._conn is not None
        dim = int(self.embedder.dim)

        for collection, table in _VEC_TABLE.items():
            self._ensure_vec_table(table, dim)

        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vec_meta (
                collection TEXT NOT NULL,
                rowid      INTEGER NOT NULL,
                biz_id     TEXT NOT NULL,
                payload    TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (collection, biz_id)
            )
            """
        )
        # 反向查询：rowid → biz_id（search 命中后取业务 id）
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_vec_meta_collection_rowid
            ON vec_meta(collection, rowid)
            """
        )

    def _ensure_vec_table(self, table: str, dim: int) -> None:
        """对单张 vec0 虚表做"建表 / 指纹检查 / 不一致重建"。"""
        assert self._conn is not None
        expected_sig = f"float[{dim}]"  # 期望的维度声明
        expected_metric = "distance_metric=cosine"

        row = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()

        if row is not None:
            existing_sql = (row["sql"] or "").lower()
            ok = (expected_sig in existing_sql) and (expected_metric in existing_sql)
            if ok:
                return  # 维度+距离类型都对，直接复用
            logger.warning(
                "KG VectorStore: 检测到 %s schema 不匹配，DROP 重建 (existing=%s, expected dim=%d cosine)",
                table,
                existing_sql.strip(),
                dim,
            )
            # 同时清掉对应 collection 的 meta，避免遗留 rowid 反查空 payload
            target_collection = next(
                (c for c, t in _VEC_TABLE.items() if t == table), None
            )
            self._conn.execute(f"DROP TABLE {table}")
            if target_collection:
                self._conn.execute(
                    "DELETE FROM vec_meta WHERE collection=?", (target_collection,)
                )

        self._conn.execute(
            f"""
            CREATE VIRTUAL TABLE {table}
            USING vec0(embedding float[{dim}] distance_metric=cosine)
            """
        )

    # ---------------- 写 ----------------

    def upsert(
        self,
        collection: str,
        biz_id: str,
        text: str,
        payload: dict,
    ) -> tuple[str, str]:
        """
        写入/更新单条向量。返回 (vector_id, embedding_model)。
        若向量通道未启用或文本为空，返回 ("", "")。
        """
        if not self.enabled or not text or self._conn is None:
            return "", ""
        if collection not in _VEC_TABLE:
            logger.warning("KG VectorStore: 未知 collection=%s", collection)
            return "", ""

        try:
            vec = self.embedder.embed_one(text)
            if not vec:
                return "", ""
            rowid = _biz_to_rowid(collection, biz_id)
            self._upsert_row(collection, rowid, biz_id, vec, payload)
            return str(rowid), self.embedder.model
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "KG VectorStore: upsert 失败 collection=%s biz_id=%s err=%s",
                collection,
                biz_id,
                exc,
            )
            return "", ""

    def upsert_many(
        self,
        collection: str,
        items: list[tuple[str, str, dict]],
    ) -> list[tuple[str, str]]:
        """
        批量写入：items=[(biz_id, text, payload), ...]
        返回每条的 (vector_id, embedding_model)；失败的位置返回 ("","")。
        """
        if not self.enabled or not items or self._conn is None:
            return [("", "") for _ in items]
        if collection not in _VEC_TABLE:
            logger.warning("KG VectorStore: 未知 collection=%s", collection)
            return [("", "") for _ in items]

        texts = [t for _, t, _ in items]
        try:
            vecs = self.embedder.embed_many(texts)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("KG VectorStore: embed_many 失败 err=%s", exc)
            return [("", "") for _ in items]

        result: list[tuple[str, str]] = []
        # 全量 upsert 走一个事务，失败回滚但不影响成功部分的语义保持简单。
        try:
            with self._lock:
                self._conn.execute("BEGIN")
                try:
                    for (biz_id, _text, payload), vec in zip(items, vecs):
                        if not vec:
                            result.append(("", ""))
                            continue
                        rowid = _biz_to_rowid(collection, biz_id)
                        self._upsert_row_unlocked(
                            collection, rowid, biz_id, vec, payload
                        )
                        result.append((str(rowid), self.embedder.model))
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("KG VectorStore: 批量 upsert 失败 err=%s", exc)
            return [("", "") for _ in items]
        return result

    def _upsert_row(
        self,
        collection: str,
        rowid: int,
        biz_id: str,
        vec: list[float],
        payload: dict,
    ) -> None:
        """单条 upsert，带锁（单条写入也要走事务来保证 vec 表与 meta 表一致）。"""
        with self._lock:
            self._conn.execute("BEGIN")  # type: ignore[union-attr]
            try:
                self._upsert_row_unlocked(collection, rowid, biz_id, vec, payload)
                self._conn.execute("COMMIT")  # type: ignore[union-attr]
            except Exception:
                self._conn.execute("ROLLBACK")  # type: ignore[union-attr]
                raise

    def _upsert_row_unlocked(
        self,
        collection: str,
        rowid: int,
        biz_id: str,
        vec: list[float],
        payload: dict,
    ) -> None:
        """假定调用者已持有 self._lock 且已 BEGIN。

        为何先 DELETE 再 INSERT：sqlite-vec 的 vec0 虚表不支持 INSERT OR REPLACE，
        但支持显式 DELETE + INSERT，幂等性由我们这里保证。
        """
        assert self._conn is not None
        table = _VEC_TABLE[collection]
        blob = _vec_to_blob(vec)

        # 1) vec 表：删旧插新
        self._conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (rowid,))
        self._conn.execute(
            f"INSERT INTO {table}(rowid, embedding) VALUES (?, ?)",
            (rowid, blob),
        )

        # 2) meta 表：upsert
        self._conn.execute(
            """
            INSERT INTO vec_meta(collection, rowid, biz_id, payload)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(collection, biz_id) DO UPDATE SET
                rowid = excluded.rowid,
                payload = excluded.payload
            """,
            (collection, rowid, biz_id, json.dumps(payload, ensure_ascii=False)),
        )

    # ---------------- 读 ----------------

    def search(
        self,
        collection: str,
        query_text: str,
        top_k: int = 10,
        concept_ids: Optional[list[str]] = None,  # 兼容旧签名，目前未使用
    ) -> list[dict]:
        """
        语义检索。返回 [{biz_id, score, payload}]。

        score 语义保持与旧 Qdrant 一致：越大越接近。
        虚表建表时已指定 distance_metric=cosine，v.distance 直接是"余弦距离"
        (范围 [0, 2])，所以 score = 1 - distance 即真正的余弦相似度，范围 [-1, 1]：
            完全同义 → 1，完全无关 → 0，完全相反 → -1。

        concept_ids 入参保留是为了兼容旧 API；当前上层调用方都没用过它，
        所以这里不做内置过滤——上层（如 facet_repo）自己在结果里 Python 侧过滤即可。
        """
        del concept_ids  # 保留参数仅为签名兼容
        if not self.enabled or not query_text or self._conn is None:
            return []
        if collection not in _VEC_TABLE:
            return []

        try:
            qvec = self.embedder.embed_one(query_text)
            if not qvec:
                return []
            return self.search_by_vector(collection, qvec, top_k=top_k)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "KG VectorStore: search 失败 collection=%s err=%s", collection, exc
            )
            return []

    def search_by_vector(
        self,
        collection: str,
        query_vec: list[float],
        top_k: int = 10,
    ) -> list[dict]:
        """直接用现成的 query 向量检索（不再走 embedder）。

        给"已经在外部算好/融合好查询向量"的场景使用，例如关系语义融合召回:
        把概念名 embedding 与某种关系的 probe 均值向量混合后,直接用混合向量
        来 search,避免每路召回都重新调用一次 embedder。

        返回值结构与 ``search()`` 一致: [{biz_id, score, payload}]。
        """
        if not self.enabled or self._conn is None:
            return []
        if collection not in _VEC_TABLE:
            return []
        if not query_vec:
            return []

        try:
            blob = _vec_to_blob(query_vec)
            table = _VEC_TABLE[collection]

            with self._lock:
                rows = self._conn.execute(
                    f"""
                    SELECT v.rowid AS rowid, v.distance AS distance,
                           m.biz_id AS biz_id, m.payload AS payload
                    FROM {table} v
                    LEFT JOIN vec_meta m
                      ON m.collection = ? AND m.rowid = v.rowid
                    WHERE v.embedding MATCH ?
                      AND k = ?
                    ORDER BY v.distance
                    """,
                    (collection, blob, int(top_k)),
                ).fetchall()

            out: list[dict] = []
            for r in rows:
                biz_id = r["biz_id"] or ""
                if not biz_id:
                    # meta 缺失（理论不应发生），跳过
                    continue
                try:
                    payload = json.loads(r["payload"] or "{}")
                except Exception:  # pylint: disable=broad-except
                    payload = {}
                # cosine 距离 → 余弦相似度。范围 [-1, 1]，越大越像
                score = 1.0 - float(r["distance"])
                out.append(
                    {
                        "biz_id": biz_id,
                        "score": score,
                        "payload": payload,
                    }
                )
            return out
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "KG VectorStore: search_by_vector 失败 collection=%s err=%s",
                collection,
                exc,
            )
            return []

    # ---------------- 删 ----------------

    def delete(self, collection: str, biz_id: str) -> None:
        if not self.enabled or self._conn is None:
            return
        if collection not in _VEC_TABLE:
            return
        try:
            rowid = _biz_to_rowid(collection, biz_id)
            table = _VEC_TABLE[collection]
            with self._lock:
                self._conn.execute("BEGIN")
                try:
                    self._conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (rowid,))
                    self._conn.execute(
                        "DELETE FROM vec_meta WHERE collection = ? AND biz_id = ?",
                        (collection, biz_id),
                    )
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "KG VectorStore: delete 失败 collection=%s biz_id=%s err=%s",
                collection,
                biz_id,
                exc,
            )

    def delete_many(self, collection: str, biz_ids: list[str]) -> None:
        if not self.enabled or not biz_ids or self._conn is None:
            return
        if collection not in _VEC_TABLE:
            return
        try:
            table = _VEC_TABLE[collection]
            rowids = [_biz_to_rowid(collection, b) for b in biz_ids]
            with self._lock:
                self._conn.execute("BEGIN")
                try:
                    # vec0 不支持 IN (...)，逐条删
                    for rid in rowids:
                        self._conn.execute(
                            f"DELETE FROM {table} WHERE rowid = ?", (rid,)
                        )
                    placeholders = ",".join("?" for _ in biz_ids)
                    self._conn.execute(
                        f"DELETE FROM vec_meta WHERE collection = ? AND biz_id IN ({placeholders})",
                        (collection, *biz_ids),
                    )
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "KG VectorStore: delete_many 失败 collection=%s err=%s",
                collection,
                exc,
            )

    # ---------------- 生命周期 ----------------

    def close(self) -> None:
        """主动关闭底层连接。可重复调用。"""
        conn = self._conn
        if conn is None:
            return
        self._conn = None
        try:
            conn.close()
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("KG VectorStore: close 失败 err=%s", e)

    def __del__(self) -> None:  # pragma: no cover
        try:
            self.close()
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("KG VectorStore: __del__ close 失败 err=%s", e)


# ---------------- 单例 ----------------

_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore(get_embedder())
    return _store
