"""
viz_registry.py — EduViz SDK 能力注册表（单一数据源）

所有与 SDK 能力相关的枚举、白名单、正则均在此定义。
validate_viz_code.py 和 generate_viz.py 均从此处读取，
新增控件/库/pattern 只需改这一个文件（或在 patterns/ 目录加文件）。
"""

from __future__ import annotations

from pathlib import Path

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
    if not viz_pattern or not _PATTERNS_DIR.exists():
        return {"name": viz_pattern}
    key = viz_pattern.split("|")[0].strip().lower().replace(" ", "_")
    candidate = _PATTERNS_DIR / f"{key}.md"
    if not candidate.exists():
        return {"name": viz_pattern}
    try:
        text = candidate.read_text(encoding="utf-8")
        meta, _ = _parse_frontmatter(text)
        meta.setdefault("name", key)
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
    if not viz_pattern or not _PATTERNS_DIR.exists():
        return ""
    key = viz_pattern.split("|")[0].strip().lower().replace(" ", "_")
    candidate = _PATTERNS_DIR / f"{key}.md"
    if candidate.exists():
        try:
            return candidate.read_text(encoding="utf-8")
        except Exception:  # pylint: disable=broad-except
            pass
    return ""
