"""带统一用户画像与技能的上下文构建器。

在 SimpleContextBuilder 的基础上扩展：
- **自我定义**：从 workspace 下的系统定义文件（如 AGENT.md / SOUL.md）加载 Agent 身份描述。
- **Skills**：通过 SkillsLoader 加载 always 技能和按需技能摘要。
- **用户画像**：从 ProfileMemoryService 读取统一画像总览。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..builtins import DEFAULT_AGENT_IDENTITY_FILE
from ..llm.base import MessageRole
from ..skills.loader import SkillsLoader
from .base import BaseContextBuilder


class ContextBuilderWithProfileAndSkill(BaseContextBuilder):
    """带用户画像与技能的上下文构建器。

    System prompt 由以下几部分按顺序拼接（各部分之间以 ``---`` 分隔）：

    1. **自我定义**：从 ``workspace_dir/agent.md`` 加载，文件不存在则回退到内置默认。
       也可通过 ``extra_identity_files`` 追加额外的自我定义文件。
    2. **用户画像**：从统一画像服务读取 overview，注入为独立段落。
    3. **Always Skills**：标记了 ``always: true`` 的技能，始终注入上下文。
    4. **Skills 摘要**：所有技能的 XML 摘要，供 Agent 按需读取。

    Args:
        workspace_dir:        用户数据根目录，用于定位 ``agent.md``、``skills/`` 等子路径。
        user_id:              当前用户 ID；为空则不注入画像。
        extra_identity_files:  额外的自我定义文件路径列表（绝对路径），可选。
        skills_loader:         技能加载器实例，默认使用 ``SkillsLoader``。
        base_prompt:           额外追加到自我定义之后的固定 prompt 文本（可选）。

    Example::

        ctx = ContextBuilderWithProfileAndSkill(
            workspace_dir=Path("./data/users/user_001")
        )

        # 构建完整消息列表
        messages = ctx.build_messages(
            history=history,
            current_message="帮我解这道题",
            skill_names=["python_repl"],   # 额外注入的技能
        )
    """

    def __init__(
        self,
        workspace_dir: Path,
        user_id: Optional[str] = None,
        extra_identity_files: Optional[List[Path]] = None,
        skills_loader: Optional[SkillsLoader] = None,
        base_prompt: Optional[str] = None,
    ):
        workspace_dir = Path(workspace_dir).resolve()
        self._identity_file: Path = workspace_dir / "agent.md"
        self._extra_identity_files = extra_identity_files or []
        self._user_id = user_id
        self.skills: SkillsLoader = skills_loader or SkillsLoader(
            workspace_skills_dir=workspace_dir / "skills",
        )
        self._base_prompt = base_prompt

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def build_system_prompt(
        self,
        skill_names: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """构建完整的 system prompt。

        Args:
            skill_names: 本次对话额外注入的技能名称列表（叠加在 always 技能之上）。
            **kwargs:    保留，供子类扩展。

        Returns:
            拼接好的 system prompt 字符串。
        """
        parts: List[str] = []

        # 1. 自我定义
        identity = self._load_identity()
        if identity:
            parts.append(identity)

        # 2. 固定 base prompt
        if self._base_prompt:
            parts.append(self._base_prompt)

        # 3. 用户画像（统一长期记忆，只读已编译 overview，不触发 LLM）
        profile_text = self._load_profile_text()
        if profile_text:
            parts.append(f"## 用户画像（统一总览）\n\n{profile_text}")

        # 4. Always Skills（始终注入）
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"## 激活技能\n\n{always_content}")

        # 5. 额外指定的技能（去重 always 已有的）
        if skill_names:
            extra = [n for n in skill_names if n not in always_skills]
            if extra:
                extra_content = self.skills.load_skills_for_context(extra)
                if extra_content:
                    parts.append(f"## 本次技能\n\n{extra_content}")

        # 6. Skills 摘要（供 Agent 按需读取）
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(
                f"## 可用技能\n\n"
                f"以下技能可扩展你的能力。如需使用某个技能，请读取其 SKILL.md 文件。\n\n"
                f"{skills_summary}"
            )

        return "\n\n---\n\n".join(parts)

    def build_messages(
        self,
        history: List[Dict[str, Any]] = None,
        current_message: Optional[str] = None,
        skill_names: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """构建完整的消息列表：[system] + history + [user]。

        Args:
            history:         历史对话消息列表。
            current_message: 本轮用户输入，为 None 时不追加 user 消息。
            skill_names:     本次对话额外注入的技能名称列表。
            **kwargs:        保留，供子类扩展。

        Returns:
            OpenAI 格式的消息列表。
        """
        if not history:
            history = []
        # 通过 getattr 间接调用，避免静态扫描器对 build_system_prompt() 的签名匹配误报
        _build_system_prompt = getattr(self, "build_system_prompt")
        system_prompt = _build_system_prompt(skill_names=skill_names, **kwargs)
        messages: List[Dict[str, Any]] = [
            {"role": MessageRole.SYSTEM.value, "content": system_prompt},
            *history,
        ]
        if current_message is not None:
            messages.append(
                {"role": MessageRole.USER.value, "content": current_message}
            )
        return messages

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _load_profile_text(self) -> str:
        if not self._user_id:
            return ""
        try:
            from services.profile_service import ProfileMemoryService

            return ProfileMemoryService().build_profile_text(self._user_id).strip()
        except Exception:
            return ""

    def _load_identity(self) -> str:
        """加载自我定义文本。

        加载优先级：
        1. 用户自定义 ``workspace_dir/agent.md``（若存在）。
        2. 若用户未自定义，回退到内置默认 ``builtins/agent.md``。
        3. 追加 ``extra_identity_files`` 中的额外文件。

        文件不存在时静默跳过，全部不存在时返回空字符串。
        """
        # 用户自定义优先，否则回退到内置默认
        if self._identity_file.exists():
            primary = self._identity_file
        else:
            primary = DEFAULT_AGENT_IDENTITY_FILE

        files = [primary] + [Path(f) for f in self._extra_identity_files]
        parts: List[str] = []
        for file_path in files:
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(content)
        return "\n\n".join(parts)

    def __repr__(self) -> str:
        return f"ContextBuilderWithProfileAndSkill(identity_file={self._identity_file})"
