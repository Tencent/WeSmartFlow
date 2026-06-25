"""Agent 流式事件类型与枚举。

本模块刻意保持"叶子"地位：
- 不导入 ``agent.base`` / ``tool.registry`` / ``llm.base`` 等任何项目内部模块
- 仅依赖 Python 标准库

这样 ``agent.base``（``BaseAgent`` 实现）与 ``tool.registry``
（执行工具时 yield 事件）都可以单向依赖本模块，避免互相 import 形成环。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Union


# ============================================================
# 枚举
# ============================================================


class AgentFinishReason(Enum):
    """Agent 结束原因。"""

    STOP = "stop"  # 正常结束
    MAX_STEPS = "max_steps"  # 达到最大步数
    ERROR = "error"  # 运行时错误


# ============================================================
# 流式事件类型
# ============================================================


@dataclass
class AgentThinkChunkEvent:
    """LLM 思考过程的单个文本分片（流式输出）。"""

    delta: str  # 本次新增的文本片段
    content: str  # 截至本分片已累积的完整文本
    step: int  # 当前推理步数（从 1 开始）


@dataclass
class AgentThinkEvent:
    """LLM 完成本轮思考，汇总输出（流式结束后触发）。"""

    content: str  # LLM 输出的完整文本（Thought / 中间推理）
    step: int  # 当前推理步数（从 1 开始）


@dataclass
class AgentToolCallChunkEvent:
    """tool_call arguments 的单个分片事件（流式输出）。

    对应 LLM 层的 ToolCallDeltaEvent，透传给调用方以避免长参数静默等待。
    """

    index: int  # tool_call 在本次响应中的下标
    id: str  # tool_call id（仅首个分片携带）
    tool_name: str  # 函数名（仅首个分片携带）
    arguments_delta: str  # 本次新增的 arguments 片段
    arguments_so_far: str  # 截至本分片已累积的完整 arguments 字符串
    step: int  # 当前推理步数


@dataclass
class AgentToolCallEvent:
    """Agent 即将调用某个工具（tool_call 完整信息，流式结束后触发）。"""

    id: str
    tool_name: str
    arguments: Dict[str, Any]
    step: int
    index: int = 0  # 该工具调用在本轮 tool_calls 中的顺序（从 0 开始）


@dataclass
class AgentToolRunEvent:
    """工具执行过程中的流式事件。

    content 可以是：
    - str：普通工具输出的文本片段
    - AgentStreamEvent：AgentTool 嵌套时，子 Agent 透传上来的事件
    """

    id: str  # tool_call id，用于关联到对应的 AgentToolCallEvent
    tool_name: str
    step: int
    content: "Union[str, AgentStreamEvent]"
    index: int = 0  # 该工具调用在本轮 tool_calls 中的顺序（从 0 开始）


@dataclass
class AgentToolResultEvent:
    """工具执行完毕，返回最终结果。

    result 是工具产出的最后一个事件：
    - str：普通工具的完整文本结果
    - AgentStreamEvent：AgentTool 嵌套时子 Agent 的最后一个事件
    """

    id: str
    tool_name: str
    arguments: Dict[str, Any]
    result: "Union[str, AgentStreamEvent]"
    step: int
    index: int = 0  # 该工具调用在本轮 tool_calls 中的顺序（从 0 开始）


@dataclass
class AgentFinalEvent:
    """Agent 推理结束，产出最终回复。"""

    content: str
    finish_reason: AgentFinishReason


# ============================================================
# 业务语义事件（由工具 hook 触发，可直接推送给前端）
# ============================================================


@dataclass
class FileCreatedEvent:
    """文件（PDF 卡片等）生成完毕。"""

    file_id: str  # 相对路径，如 "{uuid}.pdf"
    title: str = ""  # 文件标题（如卡片标题）
    file_type: str = ""  # 文件类型：html / quiz / viz


@dataclass
class NodeCreatedEvent:
    """知识节点被创建。"""

    node_id: str
    title: str


@dataclass
class MasteryUpdatedEvent:
    """节点掌握度发生变化。"""

    node_id: str
    delta: float  # 本次变化量


# 所有流式事件的联合类型
AgentStreamEvent = Union[
    AgentThinkChunkEvent,
    AgentThinkEvent,
    AgentToolCallChunkEvent,
    AgentToolCallEvent,
    AgentToolRunEvent,
    AgentToolResultEvent,
    AgentFinalEvent,
    FileCreatedEvent,
    NodeCreatedEvent,
    MasteryUpdatedEvent,
]


def extract_event_text(result: "Union[str, AgentStreamEvent]") -> str:
    """从工具结果中提取可写入 history 的文本字符串。

    - str：直接返回
    - 带 content 字段的事件（AgentFinalEvent / AgentThinkEvent 等）：返回 content
    - 其他事件：返回空字符串（业务事件不携带文本，不应写入 history）
    """
    if isinstance(result, str):
        return result
    return getattr(result, "content", "")


__all__ = [
    "AgentFinishReason",
    "AgentThinkChunkEvent",
    "AgentThinkEvent",
    "AgentToolCallChunkEvent",
    "AgentToolCallEvent",
    "AgentToolRunEvent",
    "AgentToolResultEvent",
    "AgentFinalEvent",
    "FileCreatedEvent",
    "NodeCreatedEvent",
    "MasteryUpdatedEvent",
    "AgentStreamEvent",
    "extract_event_text",
]
