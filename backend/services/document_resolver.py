"""文档资源解析服务。

将 ``doc_id [+ sub_path]`` 解析为磁盘绝对路径，并完成：

1. 鉴权（doc 必须属于 user_id；不属于直接当作"不存在"处理避免侧信道泄漏）
2. 路径穿越防护（resolved 路径必须落在 documents 根目录之下）
3. 文件存在性检查

调用方只关心抛出的异常类型，不必重复实现以上检查。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config import DATA_DIR, DOCUMENTS_DIR
from models.document import DocumentSchema
from repositories.document_repo import DocumentRepository


class DocumentNotFound(Exception):
    """文档不存在 / 不属于该用户 / 主文件已丢失。"""


class AssetPathInvalid(Exception):
    """asset 子路径不合法（包含 ``..`` 或穿越 base_dir）。"""


@dataclass
class ResolvedFile:
    doc: DocumentSchema
    abs_path: Path
    is_asset: bool  # True=asset 子资源；False=doc 主资源


def _check_owner(doc: DocumentSchema, user_id: str) -> None:
    if doc.user_id != user_id:
        # 不暴露存在性差异
        raise DocumentNotFound(doc.id)


def _safe_under(p: Path, root: Path) -> Path:
    """确保 p 解析后位于 root 之下；返回 resolved Path。

    使用 ``Path.is_relative_to`` 进行严格的目录包含判断：
    - 避免 ``str.startswith`` 的前缀绕过隐患
      （例如 ``/data/docs`` 会被 ``/data/docs_evil/x`` 误判为通过）；
    - 是 SAST 工具公认的标准 sanitizer，可消除路径穿越告警。
    """
    root_resolved = root.resolve()
    full = p.resolve()
    if not full.is_relative_to(root_resolved):
        raise AssetPathInvalid(str(full))
    return full


def _sanitize_sub_path(sub_path: str) -> Path:
    """对外部传入的 ``sub_path`` 做字符串级清洗，返回可安全拼接的相对 ``Path``。

    在拼接到磁盘路径之前一次性拒掉以下危险输入，确保进入
    ``base_dir / sub_path`` 时已是"纯粹的相对子路径"：

    1. 类型 / 空值：非 str、空串、纯空白；
    2. 控制字符：``NUL`` 等可能截断 syscall 的字节；
    3. 绝对路径：以 ``/`` 或 ``\\`` 开头；
    4. Windows 盘符 / UNC：``C:\\...`` / ``\\\\server\\share``；
    5. 任意目录段为 ``..``（向上穿越）或为空（``a//b``）；
    6. ``Path`` 解析后仍是绝对路径（兜底）。

    Returns:
        已清洗的相对 ``Path``，调用方可直接 ``base_dir / result``。

    Raises:
        AssetPathInvalid: 任意一项校验失败。
    """
    if not isinstance(sub_path, str) or not sub_path or not sub_path.strip():
        raise AssetPathInvalid("empty sub_path")

    # NUL / 控制字符
    if "\x00" in sub_path:
        raise AssetPathInvalid("null byte in sub_path")

    # 统一分隔符，便于后续按段校验
    normalized = sub_path.replace("\\", "/")

    # 绝对路径 / UNC
    if normalized.startswith("/"):
        raise AssetPathInvalid(sub_path)

    # Windows 盘符（X: 开头）
    if len(normalized) >= 2 and normalized[1] == ":":
        raise AssetPathInvalid(sub_path)

    # 按段校验：禁止 ``..`` 与空段
    parts = normalized.split("/")
    for part in parts:
        if part in ("", "..", "."):
            # 空段（``a//b``）/ 上跳 / 当前目录冗余 一律拒绝
            if part == "..":
                raise AssetPathInvalid(sub_path)
            if part == "":
                raise AssetPathInvalid(sub_path)
            # ``.`` 段无害但易混淆扫描器，统一拒绝
            raise AssetPathInvalid(sub_path)

    rel = Path(*parts)
    if rel.is_absolute():
        # 极端兜底：不应到这里
        raise AssetPathInvalid(sub_path)
    return rel


def _load_doc(doc_id: str, user_id: str) -> DocumentSchema:
    doc = DocumentRepository().get_by_id(doc_id)
    if doc is None:
        raise DocumentNotFound(doc_id)
    _check_owner(doc, user_id)
    if not doc.storage_key:
        raise DocumentNotFound(doc_id)
    return doc


def resolve_main(doc_id: str, user_id: str) -> ResolvedFile:
    """解析 doc 主资源：``DATA_DIR/{storage_key}``。"""
    doc = _load_doc(doc_id, user_id)
    abs_path = _safe_under(DATA_DIR / doc.storage_key, DOCUMENTS_DIR)
    if not abs_path.is_file():
        raise DocumentNotFound(doc_id)
    return ResolvedFile(doc=doc, abs_path=abs_path, is_asset=False)


def resolve_asset(doc_id: str, sub_path: str, user_id: str) -> ResolvedFile:
    """解析 doc 主资源同目录下的伴生文件：``base_dir/{sub_path}``。

    base_dir 为主资源 ``storage_key`` 所在目录。

    流程：
    1. **入口清洗**：``_sanitize_sub_path`` 对 ``sub_path`` 做字符串级校验，
       任何疑似攻击的写法都在拼接到磁盘路径之前直接拒掉；
    2. **owner 校验**：``_load_doc`` 校验文档归属；
    3. **resolve 兜底**：``_safe_under`` 用 ``is_relative_to`` 防御
       符号链接 / 罕见解析差异导致的逃逸。
    """
    rel = _sanitize_sub_path(sub_path)

    doc = _load_doc(doc_id, user_id)

    base_dir = (DATA_DIR / doc.storage_key).resolve().parent
    target = _safe_under(base_dir / rel, base_dir)
    if not target.is_file():
        raise DocumentNotFound(doc_id)
    return ResolvedFile(doc=doc, abs_path=target, is_asset=True)
