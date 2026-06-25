"""通用输入校验工具。

集中放置易引发 SAST 路径穿越 / 注入告警的 ID 类参数校验逻辑，
避免各 router / service / repository 各自实现校验。

约定：
- 所有由 ``new_id()`` 生成的 ID（session_id / viz_id / doc_id 等）
  本质都是 UUID v4 字符串（``uuid.uuid4()``），仅允许 ``[0-9a-fA-F-]``。
  任何路径拼接前都应通过本模块校验。
"""

from __future__ import annotations

import re
import uuid as _uuid
from typing import Annotated

from fastapi import HTTPException, Path
from pydantic import AfterValidator

# UUID（任意版本）的标准格式：8-4-4-4-12 十六进制
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


# ─────────────────────────────────────────────────────────────────────
# 通用 UUID 校验
# ─────────────────────────────────────────────────────────────────────


def is_valid_uuid(value: str) -> bool:
    """判断 ``value`` 是否是合法的 UUID 字符串。"""
    return isinstance(value, str) and bool(_UUID_RE.match(value))


def ensure_uuid(value: str, *, field_name: str = "id") -> str:
    """断言 ``value`` 是合法 UUID，否则抛 ``HTTPException(400)``。

    供 service / repository 层在拼路径前显式调用做兜底。
    """
    if not is_valid_uuid(value):
        raise HTTPException(status_code=400, detail=f"非法 {field_name}")
    return value


def sanitize_uuid(value: str, *, field_name: str = "id") -> str:
    """显式净化（sanitizer）：把外部传入的字符串解析为 UUID，再以标准格式重新生成。

    设计目标：**在入口处切断 SAST 工具的污点（taint）传播链**。

    实现要点：
    - 使用 ``uuid.UUID(value)`` 严格解析输入；任何非 UUID 字符串都会抛 ``ValueError``。
    - 解析成功后使用 ``str(parsed)`` 生成一个**全新的、由可信代码构造的字符串**，
      物理上不再是用户原始输入对象。
    - 失败时统一抛 ``HTTPException(400)``，不向调用方泄露细节。

    主流 SAST 引擎（CodeQL / SonarQube / Coverity 等）将
    ``uuid.UUID(...)`` + ``str(...)`` 这一"解析 → 重格式化"模式识别为标准 sanitizer，
    经过本函数的返回值在污点分析中视为"已净化"。

    Args:
        value: 外部传入的待校验字符串（可能含路径穿越 / 注入字符）。
        field_name: 出错时用于异常详情，默认 ``"id"``。

    Returns:
        规范化后的 UUID 字符串（小写、带连字符），可安全用于路径拼接。

    Raises:
        HTTPException: status_code=400，``value`` 不是合法 UUID。
    """
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"非法 {field_name}")
    try:
        parsed = _uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail=f"非法 {field_name}") from None
    # 重新构造字符串：从此与原 value 无任何引用关系
    return str(parsed)


def _validate_uuid_pydantic(value: str) -> str:
    """供 Pydantic ``AfterValidator`` 使用的 UUID 校验器。"""
    if not is_valid_uuid(value):
        raise ValueError("非法 ID：必须为 UUID 格式")
    return value


# FastAPI Path 参数类型（通用 UUID）：
#   viz_id: UuidPath  /  doc_id: UuidPath  /  ...
UuidPath = Annotated[
    str,
    Path(
        description="UUID v4 标识符",
        pattern=_UUID_RE.pattern,
        min_length=36,
        max_length=36,
    ),
]

# Pydantic 模型字段类型（通用 UUID）：
UuidField = Annotated[str, AfterValidator(_validate_uuid_pydantic)]


# ─────────────────────────────────────────────────────────────────────
# session_id 专用别名（向后兼容）
# ─────────────────────────────────────────────────────────────────────


def is_valid_session_id(value: str) -> bool:
    """判断 ``value`` 是否是合法 session_id（UUID 格式）。"""
    return is_valid_uuid(value)


def ensure_session_id(value: str, *, field_name: str = "session_id") -> str:
    """断言 ``value`` 是合法 session_id，否则抛 ``HTTPException(400)``。"""
    return ensure_uuid(value, field_name=field_name)


def validate_session_id_pydantic(value: str) -> str:
    """供 Pydantic ``AfterValidator`` 使用的 session_id 校验器。"""
    return _validate_uuid_pydantic(value)


SessionIdPath = UuidPath
SessionIdField = UuidField


__all__ = [
    # 通用 UUID
    "is_valid_uuid",
    "ensure_uuid",
    "sanitize_uuid",
    "UuidPath",
    "UuidField",
    # session_id 兼容别名
    "is_valid_session_id",
    "ensure_session_id",
    "validate_session_id_pydantic",
    "SessionIdPath",
    "SessionIdField",
]
