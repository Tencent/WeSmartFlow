"""用户画像记忆模块。

定义用户画像的统一存储与检索接口，并提供基于文件系统的默认实现。
采用两层结构：
- **当前画像**：结构化的用户事实，全量覆盖更新，跨会话持久化。
- **画像历史**：append-only 的变更日志，带时间戳，方便回溯和 debug。

知识库检索不在此处，应作为独立 Tool 提供给 Agent 使用。
"""

from __future__ import annotations

import json
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

logger = logging.getLogger(__file__)

if TYPE_CHECKING:
    from agent_core.llm.base import BaseLLM


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class MemoryRecord:
    """一条记忆记录。

    Attributes:
        content:   记录的文本内容。
        metadata:  附加元数据（如 key、source、score、tags 等）。
        score:     检索相关性得分（写入时为 None，检索返回时填充）。
        timestamp: 写入时间戳（Unix 秒，自动填充）。
    """

    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        score_str = f", score={self.score:.4f}" if self.score is not None else ""
        return (
            f"MemoryRecord(content={self.content!r:.50}{score_str}, "
            f"metadata={self.metadata})"
        )


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------


class UserProfileStore(ABC):
    """用户画像存储抽象基类。

    提供统一的用户画像读写接口，屏蔽底层存储细节。
    子类可基于不同后端（内存、文件、向量数据库、Redis 等）实现具体逻辑。

    **核心接口**

    - ``write(content)``：全量覆盖写入当前画像。
    - ``read_full()``：读取完整的当前画像文本。
    - ``read(query, top_k)``：按 query 检索最相关的画像片段。
    - ``append_history(entry)``：追加一条画像变更历史记录。
    - ``get_history()``：读取全部画像历史。
    - ``consolidate(messages, llm_caller)``：从对话消息中自动提取并更新画像。
    - ``clear()``：清空当前画像（历史保留）。

    典型用法（在 ContextBuilder 中）::

        store: UserProfileStore = FileUserProfileStore(workspace_dir)

        # Agent 对话结束后，自动从消息中提取并更新画像
        await store.consolidate(messages, llm)

        # 构建 context 时注入画像
        full_text = store.read_full()
        # 或按 query 检索最相关片段
        records = store.read("用户的数学水平如何")
        text = store.to_text(records)
    """

    # ------------------------------------------------------------------
    # 当前画像
    # ------------------------------------------------------------------

    @abstractmethod
    def write(self, content: str) -> None:
        """全量覆盖写入当前用户画像。

        每次调用都会替换掉之前的全部画像内容。
        调用方（通常是 ``consolidate``）负责在写入前合并旧画像与新信息。

        Args:
            content: 完整的用户画像 Markdown 文本。
        """
        ...

    @abstractmethod
    def read_full(self) -> str:
        """读取完整的当前用户画像文本。

        Returns:
            画像 Markdown 文本；若尚未写入则返回空字符串。
        """
        ...

    @abstractmethod
    def read(self, query: str, top_k: int = 5) -> List[MemoryRecord]:
        """按 query 检索最相关的用户画像片段。

        对于简单的内存实现，可以直接返回完整画像包装成单条记录；
        对于向量存储实现，应做语义检索后返回 top_k 条。

        Args:
            query: 检索查询文本。
            top_k: 返回的最大记录数。

        Returns:
            按相关性降序排列的 MemoryRecord 列表。
        """
        ...

    # ------------------------------------------------------------------
    # 画像历史
    # ------------------------------------------------------------------

    @abstractmethod
    def append_history(self, entry: str) -> None:
        """追加一条画像变更历史记录（append-only）。

        建议 entry 以 ``[YYYY-MM-DD HH:MM]`` 开头，便于时间线检索。

        Args:
            entry: 本次变更的摘要文本。
        """
        ...

    @abstractmethod
    def get_history(self) -> str:
        """读取全部画像变更历史。

        Returns:
            历史记录文本（多条以换行分隔）；若无历史则返回空字符串。
        """
        ...

    # ------------------------------------------------------------------
    # 自动提取
    # ------------------------------------------------------------------

    @abstractmethod
    async def consolidate(
        self,
        messages: List[Dict[str, Any]],
        llm_caller: Any,
    ) -> bool:
        """从对话消息中自动提取并更新用户画像。

        实现应使用 LLM tool call 模式，强制 LLM 调用结构化工具输出：
        - ``profile_update``：完整的最新画像（全量，合并旧画像与新信息）。
        - ``history_entry``：本次变更摘要（带时间戳，追加到历史）。

        失败时应有降级策略（如直接 raw-archive 原始消息到历史）。

        Args:
            messages:   本轮需要处理的对话消息列表（格式同 LLM messages）。
            llm_caller: LLM 调用对象，由子类决定具体类型和调用方式。

        Returns:
            True 表示成功（含降级成功），False 表示需要重试。
        """
        ...

    # ------------------------------------------------------------------
    # 清空
    # ------------------------------------------------------------------

    @abstractmethod
    def clear(self) -> None:
        """清空当前用户画像（画像历史保留，不受影响）。"""
        ...

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def to_text(
        self,
        records: List[MemoryRecord],
        prefix: str = "## 用户画像\n",
    ) -> str:
        """将画像记录列表格式化为可注入 system prompt 的文本。

        Args:
            records: ``read()`` 返回的记录列表。
            prefix:  文本前缀。

        Returns:
            格式化后的字符串，空列表时返回空字符串。
        """
        if not records:
            return ""
        lines = [prefix]
        for r in records:
            key = r.metadata.get("key", "")
            line_prefix = f"- [{key}] " if key else "- "
            lines.append(f"{line_prefix}{r.content}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


# ---------------------------------------------------------------------------
# LLM Tool 定义（用于 consolidate）
# ---------------------------------------------------------------------------

_UPDATE_PROFILE_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": "将本轮对话中提取到的用户信息保存到用户画像。",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": (
                            "本次变更摘要，以 [YYYY-MM-DD HH:MM] 开头，"
                            "简要描述本轮对话中发现的新用户信息。"
                        ),
                    },
                    "profile_update": {
                        "type": "string",
                        "description": (
                            "完整的最新用户画像（Markdown 格式）。"
                            "必须包含旧画像的全部内容，再合并本轮新信息。"
                            "若本轮无新信息，原样返回旧画像。"
                        ),
                    },
                },
                "required": ["history_entry", "profile_update"],
            },
        },
    }
]

_TOOL_CHOICE_FORCED = {"type": "function", "function": {"name": "update_profile"}}

# 触发降级的错误关键词（provider 不支持 forced tool_choice 时）
_TOOL_CHOICE_ERROR_MARKERS = (
    "tool_choice",
    "toolchoice",
    "does not support",
    'should be ["none", "auto"]',
)


def _is_tool_choice_unsupported(content: str | None) -> bool:
    text = (content or "").lower()
    return any(m in text for m in _TOOL_CHOICE_ERROR_MARKERS)


def _parse_tool_args(raw: Any) -> dict | None:
    """将 LLM 返回的 tool arguments 统一解析为 dict。"""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if isinstance(raw, list):
        raw = raw[0] if raw and isinstance(raw[0], dict) else None
    return raw if isinstance(raw, dict) else None


def _format_messages_for_prompt(messages: List[Dict[str, Any]]) -> str:
    """将消息列表格式化为可读文本，用于 consolidate prompt。"""
    lines = []
    for msg in messages:
        content = msg.get("content")
        if not content:
            continue
        role = msg.get("role", "unknown").upper()
        ts = msg.get("timestamp", "")
        ts_str = f"[{ts[:16]}] " if ts else ""
        lines.append(f"{ts_str}{role}: {content}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 具体实现：基于文件系统
# ---------------------------------------------------------------------------


class FileUserProfileStore(UserProfileStore):
    """基于文件系统的用户画像存储实现。

    目录结构由 ``UserDataLayout`` 统一定义::

        <root>/
        └── profile/
            ├── profile.md      # 当前用户画像（全量覆盖）
            └── history.md      # 画像变更历史（append-only）

    ``consolidate`` 使用 LLM tool call 模式自动从对话中提取用户信息，
    失败超过阈值后降级为直接 raw-archive 原始消息到 history.md。

    Args:
        profile_file:  画像文件路径（``profile.md``）。
        history_file:  画像历史文件路径（``history.md``）。
        max_failures:  连续失败多少次后触发 raw-archive 降级，默认 3。
    """

    _MAX_FAILURES = 3

    def __init__(self, profile_file: Path, history_file: Path, max_failures: int = 3):
        self._profile_file = profile_file
        self._history_file = history_file
        self._profile_file.parent.mkdir(parents=True, exist_ok=True)
        self._max_failures = max_failures
        self._consecutive_failures = 0

    # ------------------------------------------------------------------
    # 当前画像
    # ------------------------------------------------------------------

    def write(self, content: str) -> None:
        """全量覆盖写入 PROFILE.md。"""
        self._profile_file.write_text(content, encoding="utf-8")
        logger.debug("UserProfile written ({} chars)", len(content))

    def read_full(self) -> str:
        """读取 PROFILE.md，不存在时返回空字符串。"""
        if self._profile_file.exists():
            return self._profile_file.read_text(encoding="utf-8")
        return ""

    def read(self, query: str, top_k: int = 5) -> List[MemoryRecord]:
        """简单实现：将完整画像按段落切分，返回前 top_k 段。

        对于文件存储，不做语义检索，直接按段落顺序返回。
        如需语义检索，请使用向量存储子类。

        Args:
            query: 检索查询（文件实现中暂不使用，保留接口兼容性）。
            top_k: 最多返回的段落数。

        Returns:
            MemoryRecord 列表，每条对应一个非空段落。
        """
        full = self.read_full()
        if not full:
            return []

        # 按空行切分段落
        paragraphs = [p.strip() for p in full.split("\n\n") if p.strip()]
        records = []
        for i, para in enumerate(paragraphs[:top_k]):
            records.append(
                MemoryRecord(
                    content=para,
                    metadata={"index": i, "source": "PROFILE.md"},
                )
            )
        return records

    # ------------------------------------------------------------------
    # 画像历史
    # ------------------------------------------------------------------

    def append_history(self, entry: str) -> None:
        """追加一条记录到 HISTORY.md。"""
        with open(self._history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")
        logger.debug("UserProfile history appended")

    def get_history(self) -> str:
        """读取 HISTORY.md，不存在时返回空字符串。"""
        if self._history_file.exists():
            return self._history_file.read_text(encoding="utf-8")
        return ""

    # ------------------------------------------------------------------
    # 自动提取
    # ------------------------------------------------------------------

    async def consolidate(
        self,
        messages: List[Dict[str, Any]],
        llm_caller: "BaseLLM",
    ) -> bool:
        """从对话消息中自动提取用户信息并更新画像。

        流程：
        1. 构造 prompt，包含当前画像 + 本轮对话。
        2. 强制 LLM 调用 ``update_profile`` 工具输出结构化结果。
        3. 解析结果，写入 PROFILE.md 和 HISTORY.md。
        4. 失败时计数，超过阈值则 raw-archive 降级。

        Args:
            messages:   本轮对话消息列表。
            llm_caller: ``BaseLLM`` 实例。

        Returns:
            True 表示成功（含降级成功），False 表示本次失败需重试。
        """
        if not messages:
            return True

        current_profile = self.read_full()
        conversation_text = _format_messages_for_prompt(messages)

        prompt = (
            f"请分析以下对话，提取用户的个人信息、学习偏好、能力水平等有价值的信息，"
            f"调用 update_profile 工具更新用户画像。\n\n"
            f"## 当前用户画像\n{current_profile or '（暂无）'}\n\n"
            f"## 本轮对话\n{conversation_text}"
        )

        chat_messages = [
            {
                "role": "system",
                "content": (
                    "你是一个用户画像提取助手。"
                    "从对话中提取用户信息，调用 update_profile 工具保存结果。"
                    "画像需合并旧内容与新信息，保持完整性。"
                ),
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = await llm_caller.async_think(
                messages=chat_messages,
                tools=_UPDATE_PROFILE_TOOL,
                tool_choice=_TOOL_CHOICE_FORCED,
            )

            # 部分 provider 不支持 forced tool_choice，降级为 auto
            if response.is_error and _is_tool_choice_unsupported(response.content):
                logger.warning("Forced tool_choice unsupported, retrying with auto")
                response = await llm_caller.async_think(
                    messages=chat_messages,
                    tools=_UPDATE_PROFILE_TOOL,
                    tool_choice="auto",
                )

            if not response.has_tool_calls:
                logger.warning(
                    "Profile consolidation: LLM did not call update_profile "
                    "(finish_reason={}, preview={})",
                    response.finish_reason,
                    (response.content or "")[:200],
                )
                return self._on_failure(messages)

            args = _parse_tool_args(response.tool_calls[0].arguments)
            if args is None:
                logger.warning("Profile consolidation: failed to parse tool arguments")
                return self._on_failure(messages)

            history_entry = args.get("history_entry", "").strip()
            profile_update = args.get("profile_update", "").strip()

            if not history_entry or not profile_update:
                logger.warning(
                    "Profile consolidation: missing required fields in tool args"
                )
                return self._on_failure(messages)

            # 写入画像和历史
            if profile_update != current_profile:
                self.write(profile_update)
            self.append_history(history_entry)

            self._consecutive_failures = 0
            logger.info("Profile consolidation done for %s messages", len(messages))
            return True

        except Exception:  # pylint: disable=broad-except
            logger.exception("Profile consolidation raised an exception")
            return self._on_failure(messages)

    def _on_failure(self, messages: List[Dict[str, Any]]) -> bool:
        """失败计数，超过阈值后 raw-archive 降级。"""
        self._consecutive_failures += 1
        if self._consecutive_failures < self._max_failures:
            return False
        # 降级：直接把原始消息写入历史
        self._raw_archive(messages)
        self._consecutive_failures = 0
        return True

    def _raw_archive(self, messages: List[Dict[str, Any]]) -> None:
        """降级策略：将原始消息直接追加到 HISTORY.md。"""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        raw_text = _format_messages_for_prompt(messages)
        self.append_history(
            f"[{ts}] [RAW-ARCHIVE] {len(messages)} 条消息（LLM 提取失败，原始存档）\n{raw_text}"
        )
        logger.warning(
            "Profile consolidation degraded: raw-archived {} messages", len(messages)
        )

    # ------------------------------------------------------------------
    # 清空
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """清空 PROFILE.md（HISTORY.md 保留）。"""
        if self._profile_file.exists():
            self._profile_file.unlink()
        logger.info("UserProfile cleared")

    def __repr__(self) -> str:
        return f"FileUserProfileStore(profile={self._profile_file})"
