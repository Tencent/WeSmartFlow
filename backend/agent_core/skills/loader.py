"""Skills loader for agent capabilities."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

# 内置 skills 目录
from ..builtins import BUILTIN_SKILLS_DIR


logger = logging.getLogger(__name__)


class SkillsLoader:
    """Agent skills 加载器。

    Skills 是存放在目录中的 Markdown 文件（``SKILL.md``），用于向 Agent 传授
    如何使用特定工具或完成特定任务的知识。

    目录优先级（高 → 低）：
        1. workspace skills：``<workspace>/skills/<name>/SKILL.md``
        2. 内置 skills：``new_core/skills/builtin/<name>/SKILL.md``

    SKILL.md 支持可选的 YAML frontmatter，格式如下::

        ---
        description: 简短描述
        always: true          # 是否始终注入上下文
        requires:
          bins: [git, curl]   # 需要的命令行工具
          env: [API_KEY]      # 需要的环境变量
        ---

        # Skill 正文 ...

    由于框架不强依赖 PyYAML，frontmatter 采用简单的行解析；
    ``requires`` 字段支持 JSON 格式的值（``["git","curl"]``）。
    """

    def __init__(
        self,
        workspace_skills_dir: Optional[Path] = None,
        builtin_skills_dir: Optional[Path] = None,
    ):
        """
        Args:
            workspace_skills_dir: 用户自定义技能目录路径，为 None 时不加载用户技能。
            builtin_skills_dir:   内置 skills 目录，默认为 ``agent_core/builtins/skills/``。
        """
        self.workspace_skills: Optional[Path] = (
            Path(workspace_skills_dir) if workspace_skills_dir else None
        )
        self.builtin_skills: Path = builtin_skills_dir or BUILTIN_SKILLS_DIR
        self._cache: Dict[str, Optional[str]] = {}  # name → raw content

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def list_skills(self, filter_unavailable: bool = True) -> List[Dict[str, str]]:
        """列出所有可用 skills。

        Args:
            filter_unavailable: 为 True 时过滤掉依赖不满足的 skill。

        Returns:
            skill 信息列表，每项包含 ``name``、``path``、``source`` 字段。
        """
        skills: List[Dict[str, str]] = []

        # workspace skills（优先级最高）
        if self.workspace_skills and self.workspace_skills.exists():
            for skill_dir in sorted(self.workspace_skills.iterdir()):
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skills.append(
                            {
                                "name": skill_dir.name,
                                "path": str(skill_file),
                                "source": "workspace",
                            }
                        )

        # 内置 skills（workspace 同名 skill 优先）
        if self.builtin_skills and self.builtin_skills.exists():
            existing_names = {s["name"] for s in skills}
            for skill_dir in sorted(self.builtin_skills.iterdir()):
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists() and skill_dir.name not in existing_names:
                        skills.append(
                            {
                                "name": skill_dir.name,
                                "path": str(skill_file),
                                "source": "builtin",
                            }
                        )

        if filter_unavailable:
            return [
                s
                for s in skills
                if self._check_requirements(self._get_skill_meta(s["name"]))
            ]
        return skills

    def load_skill(self, name: str) -> Optional[str]:
        """按名称加载 skill 原始内容（含 frontmatter）。

        Args:
            name: skill 名称（目录名）。

        Returns:
            skill 文件内容，未找到时返回 None。
        """
        if name in self._cache:
            return self._cache[name]

        # workspace 优先
        if self.workspace_skills:
            workspace_skill = self.workspace_skills / name / "SKILL.md"
            if workspace_skill.exists():
                content = workspace_skill.read_text(encoding="utf-8")
                self._cache[name] = content
                return content

        # 内置
        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                content = builtin_skill.read_text(encoding="utf-8")
                self._cache[name] = content
                return content

        self._cache[name] = None
        return None

    def load_skills_for_context(self, skill_names: List[str]) -> str:
        """加载指定 skills 并格式化为可注入上下文的字符串。

        Args:
            skill_names: 要加载的 skill 名称列表。

        Returns:
            格式化后的 skills 内容字符串，各 skill 之间以分隔线隔开。
        """
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                body = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{body}")
            else:
                logger.warning("[SkillsLoader] skill '%s' 未找到，已跳过", name)

        return "\n\n---\n\n".join(parts) if parts else ""

    def get_always_skills(self) -> List[str]:
        """返回标记了 ``always: true`` 且依赖满足的 skill 名称列表。"""
        result = []
        for s in self.list_skills(filter_unavailable=True):
            meta = self.get_skill_metadata(s["name"]) or {}
            skill_meta = self._get_skill_meta(s["name"])
            # 支持 frontmatter 顶层 always 或 metadata 内嵌 always
            if skill_meta.get("always") or meta.get("always") in ("true", True):
                result.append(s["name"])
        return result

    def build_skills_summary(self, exclude: set = None) -> str:
        """构建 skills 的 XML 摘要（含可用性、描述、路径）。

        Args:
            exclude: 要排除的 skill 名称集合（已注入上下文的无需重复列出）。

        Returns:
            XML 格式的 skills 摘要字符串，无 skills 时返回空字符串。
        """
        exclude = exclude or set()
        all_skills = self.list_skills(filter_unavailable=False)
        all_skills = [s for s in all_skills if s["name"] not in exclude]
        if not all_skills:
            return ""

        def _esc(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        lines = ["<skills>"]
        for s in all_skills:
            skill_meta = self._get_skill_meta(s["name"])
            available = self._check_requirements(skill_meta)

            lines.append(f'  <skill available="{str(available).lower()}">')
            lines.append(f"    <name>{_esc(s['name'])}</name>")
            lines.append(
                f"    <description>{_esc(self._get_skill_description(s['name']))}</description>"
            )
            lines.append(f"    <location>{s['path']}</location>")

            if not available:
                missing = self._get_missing_requirements(skill_meta)
                if missing:
                    lines.append(f"    <requires>{_esc(missing)}</requires>")

            lines.append("  </skill>")
        lines.append("</skills>")

        return "\n".join(lines)

    def get_skill_metadata(self, name: str) -> Optional[Dict[str, str]]:
        """解析 skill frontmatter，返回键值字典。

        Args:
            name: skill 名称。

        Returns:
            frontmatter 键值字典，无 frontmatter 或未找到时返回 None。
        """
        content = self.load_skill(name)
        if not content:
            return None
        return self._parse_frontmatter(content)

    def invalidate_cache(self, name: Optional[str] = None) -> None:
        """清除缓存。

        Args:
            name: 指定 skill 名称时只清除该条；为 None 时清除全部。
        """
        if name is None:
            self._cache.clear()
        else:
            self._cache.pop(name, None)

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    def _parse_frontmatter(self, content: str) -> Optional[Dict[str, str]]:
        """从 Markdown 内容中解析 YAML frontmatter（简单行解析）。"""
        if not content.startswith("---"):
            return None
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return None

        metadata: Dict[str, str] = {}
        for line in match.group(1).splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                metadata[key.strip()] = value.strip().strip("\"'")
        return metadata

    def _strip_frontmatter(self, content: str) -> str:
        """去除 Markdown 内容中的 YAML frontmatter。"""
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end() :].strip()
        return content

    def _get_skill_meta(self, name: str) -> Dict:
        """获取 skill 的结构化 metadata（来自 frontmatter 的 ``metadata`` 字段，JSON 格式）。

        若 frontmatter 中有 ``requires`` 字段，也直接合并进来，
        方便不使用嵌套 JSON 的简单写法。
        """
        fm = self.get_skill_metadata(name) or {}

        # 尝试解析嵌套 JSON metadata 字段
        raw_meta = fm.get("metadata", "")
        try:
            nested: Dict = json.loads(raw_meta) if raw_meta else {}
        except (json.JSONDecodeError, TypeError):
            nested = {}

        # 将 frontmatter 顶层的 requires（JSON 列表字符串）合并
        result: Dict = dict(nested)
        if "requires" not in result and "requires" in fm:
            try:
                result["requires"] = json.loads(fm["requires"])
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("解析 skill 依赖失败: %s", e)

        return result

    def _get_skill_description(self, name: str) -> str:
        """从 frontmatter 获取 skill 描述，未找到时回退为 skill 名称。"""
        meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        return name

    def _check_requirements(self, skill_meta: Dict) -> bool:
        """检查 skill 的依赖是否满足（命令行工具 + 环境变量）。"""
        requires = skill_meta.get("requires", {})
        if not isinstance(requires, dict):
            return True
        for b in requires.get("bins", []):
            if not shutil.which(b):
                return False
        for env in requires.get("env", []):
            if not os.environ.get(env):
                return False
        return True

    def _get_missing_requirements(self, skill_meta: Dict) -> str:
        """返回未满足依赖的描述字符串。"""
        missing = []
        requires = skill_meta.get("requires", {})
        if not isinstance(requires, dict):
            return ""
        for b in requires.get("bins", []):
            if not shutil.which(b):
                missing.append(f"CLI: {b}")
        for env in requires.get("env", []):
            if not os.environ.get(env):
                missing.append(f"ENV: {env}")
        return ", ".join(missing)
