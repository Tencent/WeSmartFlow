"""
viz_registry.py — EduViz SDK 能力注册表（单一数据源）

所有与 SDK 能力相关的枚举、白名单、正则均在此定义。
validate_viz_code.py 和 generate_viz.py 均从此处读取，
新增控件/库/pattern 只需改这一个文件（或在 patterns/ 目录加文件）。
"""

from __future__ import annotations

from pathlib import Path
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# pattern 文件名合法字符集：仅允许 ASCII 字母/数字/下划线/连字符。
# 任何包含 '/'、'\'、'.'、空白等其它字符的输入都会被判定非法。
_PATTERN_KEY_RE = re.compile(r"^[a-z0-9_-]+$")

# ── 1. EduViz API 白名单 ──────────────────────────────────────────────────────
# key: API 名称
# output: True 表示该 API 会产生可见输出（用于 has_output 检测）
APIS: dict[str, dict] = {
    # 控件
    "slider": {"category": "control", "output": True},
    "timeline": {"category": "control", "output": True},
    "stepper": {"category": "control", "output": True},
    "toggle": {"category": "control", "output": True},
    "select": {"category": "control", "output": True},
    "button": {"category": "control", "output": True},
    # 画布 / 容器
    "createCanvas": {"category": "canvas", "output": True},
    "getContainer": {"category": "canvas", "output": True},
    "axis2d": {"category": "canvas", "output": True},
    # 信息展示
    "latex": {"category": "display", "output": True},
    "text": {"category": "display", "output": True},
    "metric": {"category": "display", "output": True},
    "progress": {"category": "display", "output": True},
    # 工具 / 事件
    "loadLib": {"category": "util", "output": False},
    "state": {"category": "util", "output": False},
    "emit": {"category": "util", "output": False},
    "on": {"category": "util", "output": False},
    "colors": {"category": "util", "output": False},
    "onThemeChange": {"category": "util", "output": False},
    "setTheme": {"category": "util", "output": False},
}

# ── 2. 已移除的旧版 API（命中即报错） ─────────────────────────────────────────
REMOVED_APIS: set[str] = {
    "bindPlot2D",
    "bindHeatmap",
    "bindVectorField",
    "bindParticles",
    "bindCanvas",
    "bindArray",
    "bindTree",
    "bindGraph",
    "animate",
    "stopAll",
    "buttonGroup",
    "input",
    "draggablePoint",
    "layout",
    "timer",
    "solvePDE",
    "vectorField",
    "scalarField",
    "mathUtils",
}

# ── 3. 第三方库白名单 ─────────────────────────────────────────────────────────
# key: loadLib 中使用的库名
# renderer_pattern: 用于 has_output 检测的正则（None 表示不产生直接输出）
LIBS: dict[str, dict] = {
    "p5": {"renderer_pattern": r"\bnew\s+p5\b"},
    "d3": {"renderer_pattern": r"\bd3\s*\.\s*select\b"},
    "three": {"renderer_pattern": r"\bnew\s+THREE\s*\.\s*WebGLRenderer"},
    "matter": {"renderer_pattern": r"Matter\s*\.\s*Render\s*\.\s*create"},
    "tone": {"renderer_pattern": None},
    "mathjs": {"renderer_pattern": None},
    "anime": {"renderer_pattern": None},
    "chart": {"renderer_pattern": r"\bnew\s+Chart\b"},
    "plotly": {"renderer_pattern": r"Plotly\s*\.\s*newPlot"},
    "katex": {"renderer_pattern": None},
    "cytoscape": {"renderer_pattern": r"\bcytoscape\s*\("},
}

# ── 4. 禁止的危险操作 ─────────────────────────────────────────────────────────
# 每项：(正则, 错误提示)
FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (
        r"\bwindow\s*\.\s*parent\b",
        "禁止直接访问 window.parent，请通过 EduViz API 与外层通信",
    ),
    (r"\bdocument\s*\.\s*write\b", "禁止使用 document.write（会破坏 DOM 初始化）"),
    (r"^\s*import\s+", "iframe 沙箱不支持 ES module，请用 EduViz.loadLib() 加载库"),
    (r"\brequire\s*\(", "iframe 沙箱不支持 CommonJS，请用 EduViz.loadLib() 加载库"),
    (
        r"\bwhile\s*\(\s*true\s*\)",
        "禁止 while(true) 死循环，请用 EduViz.timeline() 的 onFrame",
    ),
    (r"\bsetInterval\s*\(", "请使用 EduViz.timeline 或 stepper 替代 setInterval"),
    (r"<\s*(html|body|head|script)\b", "不要写 HTML 标签，DOM 已自动初始化"),
]

# ── 5. 派生：validate 用的扁平集合 ───────────────────────────────────────────
API_NAMES: set[str] = set(APIS.keys())
LIB_NAMES: set[str] = set(LIBS.keys())

# has_output 检测正则列表（从 APIS + LIBS 自动派生）
_output_api_names = [name for name, meta in APIS.items() if meta["output"]]
_output_api_pattern = r"EduViz\s*\.\s*(" + "|".join(_output_api_names) + r")"
_lib_renderer_patterns = [
    meta["renderer_pattern"] for meta in LIBS.values() if meta.get("renderer_pattern")
]
HAS_OUTPUT_PATTERNS: list[str] = [_output_api_pattern] + _lib_renderer_patterns

# ── 6. Patterns 目录自动扫描 + frontmatter 解析 ──────────────────────────────
_PATTERNS_DIR = (
    Path(__file__).parent.parent / "prompts" / "skills" / "eduviz_sdk" / "patterns"
)


def _resolve_pattern_path(viz_pattern: str) -> Optional[Path]:
    """将外部传入的 viz_pattern 名称安全地解析成 patterns 目录下的 .md 路径。

    安全策略（白名单查表 + 双重防御）：
      1. **白名单字符校验**：用户输入清洗后必须满足 ``[a-z0-9_-]+``；
      2. **白名单查表（核心 sanitizer）**：用户输入**仅用于**与磁盘扫描得到的
         真实文件名（``Path.stem``）做相等比较；最终用于拼路径的字符串
         来自磁盘目录扫描结果，与用户输入物理上无任何引用关系；
      3. **路径归一化兜底**：拼出的绝对路径必须位于 ``_PATTERNS_DIR`` 之下，
         防止符号链接、``..`` 残留等极端情况。

    返回 None 表示输入非法、不在白名单或目录不存在，调用方应按"找不到"处理。
    """
    if not viz_pattern or not _PATTERNS_DIR.exists():
        return None

    # ── 字符级白名单校验（仅用于尽早拒掉明显非法输入）──
    requested = str(viz_pattern).split("|")[0].strip().lower().replace(" ", "_")
    if not _PATTERN_KEY_RE.fullmatch(requested):
        logger.warning("非法 viz_pattern 名称已拒绝")
        return None

    # ── 白名单查表（SAST sanitizer）──
    # 关键：此处用 ``Path.stem`` 从磁盘目录扫描结果中取得"可信字符串"，
    # 用户输入 ``requested`` 只参与一次相等比较，不再流入后续路径拼接。
    try:
        base = _PATTERNS_DIR.resolve()
    except (OSError, RuntimeError):
        return None

    trusted_name: Optional[str] = None
    for entry in base.glob("*.md"):
        # entry.stem 来自磁盘扫描，由可信代码构造
        if entry.is_file() and entry.stem == requested:
            trusted_name = entry.stem
            break

    if trusted_name is None:
        logger.warning("viz_pattern 不在白名单中已拒绝")
        return None

    # 用可信字符串拼路径（trusted_name 与 viz_pattern 已无数据流关系）
    candidate = (base / f"{trusted_name}.md").resolve()

    # 兜底防御：必须严格落在 patterns 目录的直接子级
    if candidate.parent != base:
        logger.warning("viz_pattern 路径越界已拒绝")
        return None

    return candidate


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """
    解析 Markdown frontmatter（--- ... --- 块）。
    返回 (meta_dict, body_without_frontmatter)。
    若无 frontmatter，返回 ({}, 原文)。
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw_meta = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta, body


def list_patterns() -> list[str]:
    """返回所有可用 viz_pattern 名称（文件名去掉 .md），按字母排序。"""
    if not _PATTERNS_DIR.exists():
        return []
    return sorted(p.stem for p in _PATTERNS_DIR.glob("*.md"))


def load_pattern_meta(viz_pattern: str) -> dict[str, str]:
    """
    加载单个 pattern 的 frontmatter 元数据。
    返回包含 name / label / when_to_use / controls 等字段的字典。
    找不到文件或无 frontmatter 时返回 {"name": viz_pattern}。
    """
    candidate = _resolve_pattern_path(viz_pattern)
    if candidate is None or not candidate.exists():
        return {"name": viz_pattern}
    try:
        text = candidate.read_text(encoding="utf-8")
        meta, _ = _parse_frontmatter(text)
        meta.setdefault("name", candidate.stem)
        return meta
    except Exception:  # pylint: disable=broad-except
        return {"name": viz_pattern}


def list_patterns_with_meta() -> list[dict[str, str]]:
    """
    返回所有 pattern 的元数据列表（按文件名排序）。
    每项包含 frontmatter 中的所有字段。
    """
    return [load_pattern_meta(name) for name in list_patterns()]


def load_pattern(viz_pattern: str) -> str:
    """
    按 viz_pattern 名称加载对应示例文件的完整内容（含 frontmatter）。
    找不到返回空字符串。
    """
    candidate = _resolve_pattern_path(viz_pattern)
    if candidate is None or not candidate.exists():
        return ""
    try:
        return candidate.read_text(encoding="utf-8")
    except Exception as e:  # pylint: disable=broad-except
        logger.error("加载 pattern 文件失败: %s", e)
        return ""
