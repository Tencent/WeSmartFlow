"""路径相关工具与常量。"""

from __future__ import annotations

from pathlib import Path

from config import COURSES_DIR


def to_rel_path(abs_path: str, root: Path = COURSES_DIR) -> str:
    """将绝对路径转换为相对于课程根目录的相对路径；失败时原样返回。"""
    try:
        return str(Path(abs_path).relative_to(root))
    except ValueError:
        return abs_path
