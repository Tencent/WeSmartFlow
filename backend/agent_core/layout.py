"""用户数据目录布局。

统一定义每个用户的持久化数据路径，所有模块通过此类获取路径，
而非自行硬编码拼接。

每个用户拥有独立的 UserDataLayout 实例，对应一个数据根目录。

目录结构::

    <root>/
    ├── agent.md                    # Agent 自我定义（identity）
    ├── profile/                    # 用户画像
    │   ├── profile.md              # 当前画像（全量覆盖）
    │   └── history.md              # 画像变更历史（append-only）
    ├── skills/                     # 用户自定义技能
    │   └── <name>/
    │       └── SKILL.md
    └── courses/                    # 课程输出
        └── <course_slug>/
            ├── outline.json        # 大纲（顶层 Agent 输出）
            ├── chapter_01/
            │   ├── research.json   # 检索资料（researcher 输出）
            │   ├── chapter_01.tex  # TeX 源码（tex_writer 输出）
            │   ├── chapter_01.pdf  # 编译后 PDF
            │   ├── chapter_01_exercises.md  # 习题（exercises_generator 输出）
            │   └── images/         # 教学插图
            ├── chapter_02/
            │   └── ...
            └── ..."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _slugify(text: str) -> str:
    """将文本转为安全的目录名片段。"""
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", (text or "").strip()).strip("_")
    return slug[:60] or "untitled"


@dataclass
class CourseLayout:
    """单个课程的输出目录布局。

    管理一门课程下所有章节的文件路径，作为 Agent 间数据传递的文件系统协议。

    目录结构::

        <course_dir>/
        ├── outline.json
        ├── chapter_01/
        │   ├── research.json
        │   ├── chapter_01.tex
        │   ├── chapter_01.pdf
        │   ├── chapter_01_exercises.md
        │   └── images/
        └── ...

    Example::

        course = layout.course("太阳系")
        course.ensure_dirs()

        # 顶层 Agent 写入大纲
        course.save_outline(outline_data)

        # researcher 写入资料
        course.save_research(1, research_data)

        # tex_writer 读取资料
        research = course.load_research(1)
    """

    course_dir: Path

    def __post_init__(self) -> None:
        self.course_dir = Path(self.course_dir).resolve()
        self.outline_file: Path = self.course_dir / "outline.json"

    # ---- 章节目录 ----

    def chapter_dir(self, chapter_id: int) -> Path:
        """获取指定章节的输出目录。"""
        return self.course_dir / f"chapter_{chapter_id:02d}"

    def chapter_images_dir(self, chapter_id: int) -> Path:
        """获取指定章节的图片目录。"""
        return self.chapter_dir(chapter_id) / "images"

    # ---- 章节文件路径 ----

    def research_file(self, chapter_id: int) -> Path:
        """获取指定章节的研究资料 JSON 路径。"""
        return self.chapter_dir(chapter_id) / "research.json"

    def tex_file(self, chapter_id: int) -> Path:
        """获取指定章节的 TeX 源码路径。"""
        return self.chapter_dir(chapter_id) / f"chapter_{chapter_id:02d}.tex"

    def pdf_file(self, chapter_id: int) -> Path:
        """获取指定章节的 PDF 路径。"""
        return self.chapter_dir(chapter_id) / f"chapter_{chapter_id:02d}.pdf"

    def exercises_file(self, chapter_id: int) -> Path:
        """获取指定章节的习题 Markdown 路径。"""
        return self.chapter_dir(chapter_id) / f"chapter_{chapter_id:02d}_exercises.md"

    # ---- 大纲读写 ----

    def save_outline(self, data: Dict[str, Any]) -> Path:
        """保存课程大纲到 outline.json。"""
        self.course_dir.mkdir(parents=True, exist_ok=True)
        self.outline_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.outline_file

    @staticmethod
    def _sanitize_json(raw: str) -> str:
        """清洗 LLM 输出的 JSON：去除非法控制字符 + 修复非法反斜杠转义。

        处理两类常见问题：
        1. 非法控制字符：LLM 在 JSON 字符串值中混入 raw \\n \\r 等
        2. 非法反斜杠转义：LLM 输出 \\数、\\微 等非 JSON 合法转义序列，
           导致 json.loads 报 "Invalid \\escape" 错误。
           JSON 合法转义仅有：\\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX
        """
        import re

        # 第一步：移除 JSON 字符串值内的 raw 控制字符（\x00-\x08, \x0a-\x1f 除 \x09）
        # 保留 \t (0x09) 因为它虽需转义但 Python json 解析器能容忍
        cleaned = re.sub(r"[\x00-\x08\x0a-\x1f]", "", raw)
        # 第二步：修复非法反斜杠转义
        # 将 \ 后面不是合法 JSON 转义字符的情况，把 \ 替换为 \\（双反斜杠）
        # 合法转义字符：" \ / b f n r t u
        cleaned = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", cleaned)
        return cleaned

    def load_outline(self) -> Optional[Dict[str, Any]]:
        """加载课程大纲，文件不存在返回 None。

        自动清洗 LLM 输出中可能包含的非法 JSON 控制字符。
        """
        if not self.outline_file.exists():
            return None
        raw = self.outline_file.read_text(encoding="utf-8")
        sanitized = self._sanitize_json(raw)
        return json.loads(sanitized)

    # ---- 研究资料读写 ----

    def save_research(self, chapter_id: int, data: Dict[str, Any]) -> Path:
        """保存章节研究资料到 research.json。"""
        ch_dir = self.chapter_dir(chapter_id)
        ch_dir.mkdir(parents=True, exist_ok=True)
        path = self.research_file(chapter_id)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def load_research(self, chapter_id: int) -> Optional[Dict[str, Any]]:
        """加载章节研究资料，文件不存在返回 None。

        自动清洗 LLM 输出中可能包含的非法 JSON 控制字符。
        """
        path = self.research_file(chapter_id)
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        sanitized = self._sanitize_json(raw)
        return json.loads(sanitized)

    # ---- 目录创建 ----

    def ensure_dirs(self, chapter_ids: Optional[list] = None) -> None:
        """确保课程目录和指定章节目录存在。

        Args:
            chapter_ids: 需要创建的章节 ID 列表。为 None 时只创建课程根目录。
        """
        self.course_dir.mkdir(parents=True, exist_ok=True)
        if chapter_ids:
            for cid in chapter_ids:
                self.chapter_dir(cid).mkdir(parents=True, exist_ok=True)
                self.chapter_images_dir(cid).mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        return f"CourseLayout(course_dir={self.course_dir})"


@dataclass
class UserDataLayout:
    """用户数据目录布局。

    一个实例对应一个用户的数据根目录，所有路径在初始化时一次性计算好。

    Args:
        root: 用户数据根目录路径。

    Example::

        layout = UserDataLayout(root=Path("./data/users/user_001"))
        layout.ensure_dirs()

        # 各模块使用 layout 获取路径
        profile_store = FileUserProfileStore(layout)
        skills_loader = SkillsLoader(layout)
        ctx_builder = ContextBuilderWithProfileAndSkill(layout)

        # 课程输出
        course = layout.course("太阳系")
        course.ensure_dirs(chapter_ids=[1, 2, 3])
    """

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()

        # ---- Agent 自我定义 ----
        self.identity_file: Path = self.root / "agent.md"

        # ---- 用户画像 ----
        self.profile_dir: Path = self.root / "profile"
        self.profile_file: Path = self.profile_dir / "profile.md"
        self.profile_history_file: Path = self.profile_dir / "history.md"

        # ---- 用户自定义技能 ----
        self.skills_dir: Path = self.root / "skills"

        # ---- 课程输出 ----
        self.courses_dir: Path = self.root / "courses"

    def skill_file(self, name: str) -> Path:
        """获取指定技能的 SKILL.md 路径。

        Args:
            name: 技能名称（目录名）。

        Returns:
            ``<root>/skills/<name>/SKILL.md`` 路径。
        """
        return self.skills_dir / name / "SKILL.md"

    def course(self, topic: str) -> CourseLayout:
        """获取指定课程的 CourseLayout 实例。

        Args:
            topic: 课程主题，会被 slugify 为目录名。

        Returns:
            CourseLayout 实例，管理该课程下所有章节的文件路径。

        Example::

            course = layout.course("太阳系")
            course.ensure_dirs(chapter_ids=[1, 2, 3])
            course.save_outline({"topic": "太阳系", "chapters": [...]})
        """
        slug = _slugify(topic)
        return CourseLayout(course_dir=self.courses_dir / slug)

    def ensure_dirs(self) -> None:
        """确保所有必要目录存在。

        不会自动调用，由使用方在需要写入时手动调用。
        只读场景（如测试、检查）无需调用。
        """
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.courses_dir.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        return f"UserDataLayout(root={self.root})"
