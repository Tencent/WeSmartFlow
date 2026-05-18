"""SkillPromptContextBuilder：基于 prompt 文件 + 技能的轻量上下文构建器。

适用场景：业务侧需要"自定义 prompt 文件 + 按需注入技能 + 多轮对话历史"，
但**不需要**用户画像和 agent.md（如 tutor、extract 等专用 Agent）。

System prompt 由以下部分按顺序拼接（各部分之间以 ``---`` 分隔）：
1. 从 prompt_file（.md）读取的角色定义
2. Always Skills（标记了 always: true 的技能，始终注入）
3. 按需技能（通过 skill_names kwarg 传入）
4. Skills 摘要（供 Agent 按需读取）

build_messages 支持的 kwargs：
- chat_history: List[Any]  — 多轮对话历史（MessageSchema 列表）
- skill_names:  List[str]  — 本次额外注入的技能名称
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..llm.base import MessageRole
from ..skills.loader import SkillsLoader
from .base import BaseContextBuilder


class SkillPromptContextBuilder(BaseContextBuilder):
    """基于 prompt 文件 + 技能的上下文构建器。

    Args:
        prompt_file:   system prompt 的 .md 文件路径。
        skills_loader: SkillsLoader 实例，为 None 时不加载技能。
    """

    def __init__(
        self,
        prompt_file: Optional[Path] = None,
        skills_loader: Optional[SkillsLoader] = None,
    ):
        self._prompt_file: Optional[Path] = Path(prompt_file) if prompt_file else None
        self._skills: Optional[SkillsLoader] = skills_loader
        self._prompt_cache: Optional[str] = None

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def build_system_prompt(
        self,
        skill_names: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        parts: List[str] = []

        # 1. 从 .md 文件读取角色定义
        role_prompt = self._load_prompt_file()
        if role_prompt:
            parts.append(role_prompt)

        if self._skills:
            # 2. Always Skills（始终注入）
            always_skills = self._skills.get_always_skills()
            if always_skills:
                always_content = self._skills.load_skills_for_context(always_skills)
                if always_content:
                    parts.append(f"## 激活技能\n\n{always_content}")

            # 3. 额外指定的技能（去重 always 已有的）
            if skill_names:
                extra = [n for n in skill_names if n not in always_skills]
                if extra:
                    extra_content = self._skills.load_skills_for_context(extra)
                    if extra_content:
                        parts.append(f"## 本次技能\n\n{extra_content}")

            # 4. Skills 摘要（供 Agent 按需读取，排除已注入的）
            injected = set(always_skills or [])
            if skill_names:
                injected.update(skill_names)
            skills_summary = self._skills.build_skills_summary(exclude=injected)
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
        chat_history: Optional[List[Any]] = None,
        skill_names: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """构建完整消息列表：[system] + chat_history + history + [user]。

        Args:
            history:         Agent 内部本轮推理历史（tool calls 等）。
            current_message: 本轮用户输入。
            chat_history:    多轮对话历史（List[MessageSchema]），可选。
            skill_names:     本次额外注入的技能名称列表。
            **kwargs:        保留扩展。
        """
        if not history:
            history = []

        system_prompt = self.build_system_prompt(
            skill_names=skill_names,
            **kwargs,
        )

        # 将 MessageSchema 列表转为 OpenAI 格式
        session_messages: List[Dict[str, Any]] = []
        if chat_history:
            for msg in chat_history:
                role = msg.role if hasattr(msg, "role") else msg.get("role", "user")
                content = (
                    msg.content if hasattr(msg, "content") else msg.get("content", "")
                )
                session_messages.append({"role": role, "content": content})

        messages: List[Dict[str, Any]] = [
            {"role": MessageRole.SYSTEM.value, "content": system_prompt},
            *session_messages,
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

    def _load_prompt_file(self) -> str:
        """读取 prompt .md 文件内容，带缓存。文件不存在时返回空字符串。"""
        if self._prompt_cache is not None:
            return self._prompt_cache
        if self._prompt_file and self._prompt_file.exists():
            self._prompt_cache = self._prompt_file.read_text(encoding="utf-8").strip()
        else:
            self._prompt_cache = ""
        return self._prompt_cache

    def reload_prompt(self) -> None:
        """清除缓存，下次 build 时重新读取文件（用于热更新）。"""
        self._prompt_cache = None

    def __repr__(self) -> str:
        return f"SkillPromptContextBuilder(prompt_file={self._prompt_file})"
