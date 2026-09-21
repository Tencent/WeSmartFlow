"""Workflow — 声明式 DAG 编排。

为什么需要它（而不是让 ReAct 自由规划）：

============================  ==================================
业务实际需要                    LLM 自由规划的表现
============================  ==================================
固定 DAG（步骤确定、成本可预测）  步骤不可控、成本不可预测
细粒度进度上报（stage + pct）     无结构化进度
单步失败可续跑                   失败需整体重来
层内并行（章节间无依赖）          严格串行
============================  ==================================

**选型原则**：任务路径已知 → ``Workflow``；需要按环境反馈动态决策 →
``ReActAgent``。二者可嵌套：Workflow 的节点内部可以跑 ReAct。

本模块提供的能力：

- 拓扑分层 → 层内 ``asyncio.gather`` 并行
- 每节点完成即 checkpoint → 重启从最后成功节点续跑
- 节点级重试与超时
- 内建进度事件，无需业务侧手工 yield

.. note::
   这是**通用原语**，当前业务侧尚无生产调用方。既有的确定性流水线
   （沉浸式课程生成、court/forge）仍使用各自手写的编排——它们积累了
   大量调优行为（章节级并发、字段级就绪解锁、失败降级、前端依赖的 SSE
   事件契约），迁移需要单独一轮工作与充分回归，不宜为形式统一而仓促替换。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Set,
    runtime_checkable,
)

from ..runtime.budget import BudgetExceeded, CancelledByCaller
from ..runtime.run_context import RunContext
from ..runtime.trace import SPAN_NODE, SPAN_WORKFLOW

logger = logging.getLogger(__name__)

#: 节点执行函数签名：(inputs, ctx) -> 输出字典
#: inputs 含工作流初始输入与所有已完成上游节点的输出（按节点 id 索引）。
NodeFn = Callable[[Dict[str, Any], RunContext], Awaitable[Dict[str, Any]]]


class NodeFailed(RuntimeError):
    """节点执行失败（已耗尽重试）。"""

    def __init__(self, node_id: str, cause: BaseException):
        self.node_id = node_id
        self.cause = cause
        super().__init__(f"节点 {node_id} 执行失败: {cause}")


class NeedApproval(Exception):
    """节点需要人工审批才能继续。

    抛出此异常会让工作流在当前 checkpoint 处挂起（已完成节点的输出已持久化），
    审批通过后重新运行同一 ``run_id`` 即可续跑。
    """

    def __init__(self, node_id: str = "", detail: str = ""):
        self.node_id = node_id
        self.detail = detail
        super().__init__(detail or f"节点 {node_id} 需要人工审批")


# ----------------------------------------------------------------------
# Checkpoint
# ----------------------------------------------------------------------


@runtime_checkable
class CheckpointStore(Protocol):
    """节点输出持久化协议，用于断点续跑。"""

    async def load(self, run_id: str) -> Dict[str, Any]:
        """载入已完成节点的输出（``{node_id: output}``）。"""
        ...

    async def save(self, run_id: str, node_id: str, output: Dict[str, Any]) -> None:
        """持久化单个节点的输出。"""
        ...

    async def clear(self, run_id: str) -> None:
        """清除该次运行的所有 checkpoint。"""
        ...


class MemoryCheckpointStore:
    """内存 checkpoint（进程内有效，用于测试与短任务）。"""

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}

    async def load(self, run_id: str) -> Dict[str, Any]:
        return dict(self._data.get(run_id, {}))

    async def save(self, run_id: str, node_id: str, output: Dict[str, Any]) -> None:
        self._data.setdefault(run_id, {})[node_id] = output

    async def clear(self, run_id: str) -> None:
        self._data.pop(run_id, None)


class NullCheckpointStore:
    """不做持久化（工作流默认值，行为等价于"每次都从头跑"）。"""

    async def load(self, run_id: str) -> Dict[str, Any]:
        return {}

    async def save(self, run_id: str, node_id: str, output: Dict[str, Any]) -> None:
        return None

    async def clear(self, run_id: str) -> None:
        return None


# ----------------------------------------------------------------------
# 事件
# ----------------------------------------------------------------------


@dataclass
class WorkflowStartEvent:
    """工作流开始。"""

    run_id: str
    total_nodes: int
    skipped: List[str] = field(default_factory=list)  # 因 checkpoint 跳过的节点


@dataclass
class NodeStartEvent:
    """节点开始执行。"""

    node_id: str
    pct: int = 0


@dataclass
class NodeDoneEvent:
    """节点执行完成。"""

    node_id: str
    pct: int = 0
    duration_ms: float = 0.0
    output_keys: List[str] = field(default_factory=list)


@dataclass
class NodeSkippedEvent:
    """节点因已有 checkpoint 而跳过。"""

    node_id: str
    pct: int = 0


@dataclass
class NodeFailedEvent:
    """节点执行失败。"""

    node_id: str
    error: str
    attempts: int = 1


@dataclass
class WorkflowDoneEvent:
    """工作流全部完成。"""

    run_id: str
    outputs: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


@dataclass
class WorkflowAbortedEvent:
    """工作流中止（取消 / 预算 / 节点失败 / 待审批）。"""

    run_id: str
    reason: str
    detail: str = ""
    failed_node: str = ""


WorkflowEvent = Any  # 上述事件的联合


# ----------------------------------------------------------------------
# 节点
# ----------------------------------------------------------------------


@dataclass
class Node:
    """工作流节点。

    Attributes:
        id:       节点唯一标识，也是其输出在 inputs 中的键。
        run:      执行函数，签名见 :data:`NodeFn`。
        needs:    依赖的上游节点 id；全部完成后本节点才可执行。
        retries:  失败重试次数（0 表示不重试）。
        timeout:  单次执行超时秒数，None 表示不限。
        optional: 为 True 时本节点失败不中断工作流（输出记为空字典）。
        weight:   进度权重，用于计算 pct（默认等权）。
    """

    id: str
    run: NodeFn
    needs: tuple[str, ...] = ()
    retries: int = 0
    timeout: Optional[float] = None
    optional: bool = False
    weight: float = 1.0


# ----------------------------------------------------------------------
# 工作流
# ----------------------------------------------------------------------


class Workflow:
    """声明式 DAG 工作流。

    Example::

        COURSE = Workflow([
            Node("outline",   run=plan_outline),
            Node("research",  run=research_chapters, needs=("outline",), retries=2),
            Node("tex",       run=write_tex,      needs=("research",), retries=1),
            Node("exercises", run=gen_exercises,  needs=("tex",)),
            Node("audio",     run=gen_audio,      needs=("tex",), optional=True),
            Node("archive",   run=archive,        needs=("exercises", "audio")),
        ])

        async for ev in COURSE.stream({"topic": "太阳系"}, ctx, store=store):
            ...

    ``exercises`` 与 ``audio`` 同层，会并行执行。
    """

    def __init__(self, nodes: Sequence[Node], name: str = "workflow"):
        self.name = name
        self._nodes: Dict[str, Node] = {}
        for node in nodes:
            if node.id in self._nodes:
                raise ValueError(f"重复的节点 id: {node.id}")
            self._nodes[node.id] = node

        self._layers = self._topo_layers()
        self._order = [nid for layer in self._layers for nid in layer]

    # ------------------------------------------------------------------
    # 拓扑
    # ------------------------------------------------------------------

    def _topo_layers(self) -> List[List[str]]:
        """把 DAG 分层：同层节点无依赖关系，可并行执行。

        Raises:
            ValueError: 存在环或引用了未定义的节点。
        """
        for node in self._nodes.values():
            for dep in node.needs:
                if dep not in self._nodes:
                    raise ValueError(f"节点 {node.id} 依赖了未定义的节点 {dep}")

        remaining: Set[str] = set(self._nodes)
        done: Set[str] = set()
        layers: List[List[str]] = []

        while remaining:
            ready = sorted(
                nid
                for nid in remaining
                if all(dep in done for dep in self._nodes[nid].needs)
            )
            if not ready:
                raise ValueError(f"工作流存在循环依赖，涉及节点: {sorted(remaining)}")
            layers.append(ready)
            done.update(ready)
            remaining -= set(ready)

        return layers

    @property
    def layers(self) -> List[List[str]]:
        """拓扑分层结果（只读）。"""
        return [list(layer) for layer in self._layers]

    @property
    def node_ids(self) -> List[str]:
        """所有节点 id（拓扑顺序）。"""
        return list(self._order)

    def _progress_pct(self, completed: Dict[str, Any]) -> int:
        """按节点权重计算完成百分比。

        分子与分母必须沿同一顺序、用同一种方式求和：``sum()`` 对 float 做补偿
        求和，而逐项 ``+=`` 是朴素累加，即使加数顺序相同两者也不逐位相等。原先
        分母用 ``sum()``、分子用 ``+=`` 累加，分数权重下全部节点完成后
        ``done / total`` 会是 0.999...，被 ``int()`` 截断成 99 而不是 100。
        """
        total = sum(self._nodes[nid].weight for nid in self._order) or 1.0
        done = sum(self._nodes[nid].weight for nid in self._order if nid in completed)
        return int(done / total * 100)

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    async def stream(
        self,
        inputs: Dict[str, Any],
        ctx: RunContext,
        store: Optional[CheckpointStore] = None,
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """执行工作流，逐事件 yield 进度。

        Args:
            inputs: 初始输入，会与各节点输出合并后传给下游。
            ctx:    运行上下文（预算、取消、追踪共享给所有节点）。
            store:  checkpoint 存储；提供时已完成节点会被跳过。

        Yields:
            :data:`WorkflowEvent`
        """
        store = store or NullCheckpointStore()
        started = time.monotonic()

        completed: Dict[str, Any] = await store.load(ctx.run_id)
        skipped = [nid for nid in self.node_ids if nid in completed]

        yield WorkflowStartEvent(
            run_id=ctx.run_id, total_nodes=len(self._nodes), skipped=skipped
        )

        with ctx.tracer.span(f"workflow.{self.name}", SPAN_WORKFLOW) as wf_span:
            for layer in self._layers:
                pending = [nid for nid in layer if nid not in completed]

                for nid in layer:
                    if nid in completed and nid in skipped:
                        yield NodeSkippedEvent(
                            node_id=nid, pct=self._progress_pct(completed)
                        )

                if not pending:
                    continue

                try:
                    ctx.checkpoint()
                except CancelledByCaller as e:
                    yield WorkflowAbortedEvent(ctx.run_id, "cancelled", str(e))
                    return
                except BudgetExceeded as e:
                    yield WorkflowAbortedEvent(ctx.run_id, "budget", str(e))
                    return

                for nid in pending:
                    yield NodeStartEvent(node_id=nid, pct=self._progress_pct(completed))

                # 层内并行
                node_inputs = {**inputs, **completed}

                async def run_and_checkpoint(nid: str):
                    result = await self._run_node(self._nodes[nid], node_inputs, ctx)
                    # 独立保存已完成节点，避免同层其他节点失败时丢失成功结果。
                    await store.save(ctx.run_id, nid, result[0])
                    return result

                results = await asyncio.gather(
                    *(run_and_checkpoint(nid) for nid in pending),
                    return_exceptions=True,
                )

                for nid, result in zip(pending, results):
                    node = self._nodes[nid]

                    if isinstance(result, CancelledByCaller):
                        yield WorkflowAbortedEvent(
                            ctx.run_id, "cancelled", str(result), nid
                        )
                        return
                    if isinstance(result, BudgetExceeded):
                        yield WorkflowAbortedEvent(
                            ctx.run_id, "budget", str(result), nid
                        )
                        return
                    if isinstance(result, NeedApproval):
                        yield WorkflowAbortedEvent(
                            ctx.run_id, "need_approval", result.detail, nid
                        )
                        return

                    if isinstance(result, BaseException):
                        if node.optional:
                            logger.warning(
                                "[Workflow] 可选节点 %s 失败，继续执行: %s", nid, result
                            )
                            yield NodeFailedEvent(nid, str(result), node.retries + 1)
                            completed[nid] = {}
                            await store.save(ctx.run_id, nid, {})
                            continue

                        yield NodeFailedEvent(nid, str(result), node.retries + 1)
                        yield WorkflowAbortedEvent(
                            ctx.run_id, "node_failed", str(result), nid
                        )
                        return

                    output, elapsed_ms = result
                    completed[nid] = output

                    yield NodeDoneEvent(
                        node_id=nid,
                        pct=self._progress_pct(completed),
                        duration_ms=elapsed_ms,
                        output_keys=sorted(output.keys()) if output else [],
                    )

            wf_span.set(nodes=len(self._nodes), skipped=len(skipped))

        yield WorkflowDoneEvent(
            run_id=ctx.run_id,
            outputs=completed,
            duration_ms=(time.monotonic() - started) * 1000.0,
        )

    async def run(
        self,
        inputs: Dict[str, Any],
        ctx: RunContext,
        store: Optional[CheckpointStore] = None,
    ) -> Dict[str, Any]:
        """执行工作流并返回所有节点输出（消费 :meth:`stream` 取终态）。

        Raises:
            NodeFailed: 某个必需节点失败。
            CancelledByCaller / BudgetExceeded: 运行被中止。
        """
        outputs: Dict[str, Any] = {}
        async for event in self.stream(inputs, ctx, store):
            if isinstance(event, WorkflowDoneEvent):
                outputs = event.outputs
            elif isinstance(event, WorkflowAbortedEvent):
                if event.reason == "cancelled":
                    raise CancelledByCaller(event.detail)
                if event.reason == "budget":
                    raise BudgetExceeded("workflow", event.detail)
                if event.reason == "need_approval":
                    raise NeedApproval(event.failed_node, event.detail)
                raise NodeFailed(event.failed_node, RuntimeError(event.detail))
        return outputs

    # ------------------------------------------------------------------
    # 单节点执行
    # ------------------------------------------------------------------

    async def _run_node(
        self, node: Node, inputs: Dict[str, Any], ctx: RunContext
    ) -> tuple[Dict[str, Any], float]:
        """执行单个节点，含重试与超时。

        Returns:
            ``(输出字典, 耗时毫秒)``
        """
        started = time.monotonic()
        last_error: Optional[BaseException] = None

        for attempt in range(node.retries + 1):
            ctx.checkpoint()

            try:
                with ctx.tracer.span(
                    f"node.{node.id}", SPAN_NODE, attempt=attempt
                ) as span:
                    coro = node.run(inputs, ctx)
                    output = (
                        await asyncio.wait_for(coro, timeout=node.timeout)
                        if node.timeout
                        else await coro
                    )
                    span.set(output_keys=sorted((output or {}).keys()))

                return (output or {}), (time.monotonic() - started) * 1000.0

            except (CancelledByCaller, BudgetExceeded, NeedApproval):
                raise  # 中止类异常不重试
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(
                    "[Workflow] 节点 %s 第 %d 次执行超时（%.0fs）",
                    node.id,
                    attempt + 1,
                    node.timeout or 0,
                )
            except Exception as e:  # pylint: disable=broad-except
                last_error = e
                logger.warning(
                    "[Workflow] 节点 %s 第 %d 次执行失败: %s",
                    node.id,
                    attempt + 1,
                    e,
                )

            if attempt < node.retries:
                await asyncio.sleep(min(2**attempt, 8))  # 指数退避

        raise NodeFailed(node.id, last_error or RuntimeError("未知错误"))

    def __repr__(self) -> str:
        return f"<Workflow {self.name} nodes={len(self._nodes)} layers={len(self._layers)}>"


__all__ = [
    "CheckpointStore",
    "MemoryCheckpointStore",
    "NeedApproval",
    "Node",
    "NodeDoneEvent",
    "NodeFailed",
    "NodeFailedEvent",
    "NodeFn",
    "NodeSkippedEvent",
    "NodeStartEvent",
    "NullCheckpointStore",
    "Workflow",
    "WorkflowAbortedEvent",
    "WorkflowDoneEvent",
    "WorkflowEvent",
    "WorkflowStartEvent",
]
