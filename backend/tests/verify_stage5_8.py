"""阶段 5-8 改造验证。

覆盖：
- 阶段 5：框架零业务依赖、layout 拆分、ContextProvider 注入
- 阶段 6：AgentSettings 配置注入
- 阶段 7：声明式 Agent 注册表、业务事件、交互策略、TurnCollector
- 阶段 8：Workflow DAG、checkpoint 续跑、structured_think

运行::

    python backend/tests/verify_stage5_8.py
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASS, FAIL = "  ok  ", " FAIL "
_failures: List[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"[{PASS if cond else FAIL}] {label}" + (f"  → {extra}" if extra else ""))
    if not cond:
        _failures.append(label)


# ======================================================================
# 阶段 5：解耦
# ======================================================================


def test_no_reverse_dependency() -> None:
    print("\n── 5.1 agent_core 不反向依赖业务层 ──")

    import re

    core = Path(__file__).resolve().parents[1] / "agent_core"
    pattern = re.compile(
        r"^\s*(?:from|import)\s+"
        r"(config|database|services|repositories|models|agents|kg|court|channels)\b",
        re.MULTILINE,
    )

    offenders: List[str] = []
    for py in core.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            line_no = text[: match.start()].count("\n") + 1
            offenders.append(f"{py.relative_to(core)}:{line_no} {match.group(1)}")

    check(
        "agent_core 内无业务模块 import",
        not offenders,
        "; ".join(offenders[:5]) if offenders else "",
    )


def test_layout_split() -> None:
    print("\n── 5.2 layout 业务/框架拆分 ──")

    from agent_core.layout import AgentWorkspace, UserDataLayout, slugify

    ws = AgentWorkspace(root=Path("/tmp/ws_test"), user_id="u1")
    check(
        "AgentWorkspace 只含框架路径",
        hasattr(ws, "skills_dir") and hasattr(ws, "identity_file"),
    )
    check("AgentWorkspace 不含业务 courses_dir", not hasattr(ws, "courses_dir"))
    check(
        "slugify 已公开",
        slugify("太阳系 入门") == "太阳系_入门",
        slugify("太阳系 入门"),
    )

    from services.immersive.layout import CourseLayout

    course = CourseLayout(course_dir=Path("/tmp/course_test"))
    check(
        "CourseLayout 已迁至业务层且路径协议不变",
        course.tex_file(1).name == "chapter_01.tex"
        and course.exercises_file(3).name == "chapter_03_exercises.md",
    )

    # 兼容路径：UserDataLayout.course() 经工厂委托
    layout = UserDataLayout(root=Path("/tmp/ws_test"), user_id="u1")
    check("UserDataLayout 兼容 courses_dir", hasattr(layout, "courses_dir"))
    check(
        "UserDataLayout.course() 委托业务工厂成功",
        type(layout.course("太阳系")).__name__ == "CourseLayout",
    )


async def test_context_provider() -> None:
    print("\n── 5.3 ContextProvider 动态注入 ──")

    from agent_core.context.provider import (
        CallableProvider,
        StaticProvider,
        gather_provider_sections,
    )
    from agent_core.runtime import new_context

    class Boom:
        name = "boom"
        title = "会炸的"

        async def provide(self, ctx, user_input=""):
            raise RuntimeError("故意失败")

    ctx = new_context()
    sections = await gather_provider_sections(
        [
            StaticProvider("a", "画像内容", title="用户画像"),
            Boom(),
            CallableProvider("b", lambda c, i: f"输入是 {i}", title="回显"),
            StaticProvider("empty", ""),
        ],
        ctx,
        "测试输入",
    )

    check("provider 片段按声明顺序渲染", len(sections) == 2, f"{len(sections)} 段")
    check("带 title 的片段渲染为 ## 段落", sections[0].startswith("## 用户画像"))
    check("单个 provider 失败不影响其余", "回显" in sections[1])
    check("空片段被跳过", all(s.strip() for s in sections))

    # 接入 SystemPromptBuilder
    from agent_core.context.layered import LayeredPromptBuilder

    builder = LayeredPromptBuilder(
        providers=[StaticProvider("p", "动态片段内容", title="动态")]
    )
    prompt = await builder.build_system_prompt_async(ctx, "输入")
    check("SystemPromptBuilder 异步路径注入 provider 片段", "动态片段内容" in prompt)

    sync_prompt = builder.build_system_prompt()
    check("同步路径不含 provider 片段（无 IO）", "动态片段内容" not in sync_prompt)


# ======================================================================
# 阶段 6：配置注入
# ======================================================================


def test_settings_injection() -> None:
    print("\n── 6. AgentSettings 配置注入 ──")

    from agent_core.runtime.settings import AgentSettings

    fake_env = {
        "LLM_API_KEY": "sk-test",
        "LLM_MODEL": "qwen-plus",
        "DASHSCOPE_API_KEY": "ds-key",
        "TAVILY_API_KEY": "tv-key",
        "AGENT_HTTP_TIMEOUT": "30",
    }
    s = AgentSettings.from_env(fake_env)

    check("LLM 配置正确解析", s.llm.api_key == "sk-test" and s.llm.model == "qwen-plus")
    check("图像 Key 回退到 DASHSCOPE", s.image.api_key == "ds-key")
    check("TTS Key 回退到 DASHSCOPE", s.tts.api_key == "ds-key")
    check("搜索 Key 解析", s.search.api_key == "tv-key")
    check("整型配置解析", s.timeout == 30)
    check("available 判定", s.llm.available and not AgentSettings().llm.available)

    override = s.with_overrides(timeout=90)
    check("with_overrides 不改原对象", s.timeout == 30 and override.timeout == 90)

    # 可注入性：不依赖真实 os.environ
    empty = AgentSettings.from_env({})
    check("空环境不报错且降级为不可用", not empty.llm.available)

    ctx_settings = AgentSettings.from_env(fake_env)
    from agent_core.runtime import new_context

    ctx = new_context(settings=ctx_settings)
    check("RunContext 携带 settings", ctx.settings.llm.model == "qwen-plus")


# ======================================================================
# 阶段 7：声明式 Agent + 业务解耦
# ======================================================================


def test_agent_registry() -> None:
    print("\n── 7.1 声明式 Agent 注册表 ──")

    from agents.registry import AGENTS, get_spec

    check("已声明 5 个 Agent", len(AGENTS) == 5, str(sorted(AGENTS)))

    tutor = get_spec("tutor")
    check("tutor 声明 16 个工具", len(tutor.tools) == 16, str(len(tutor.tools)))
    check("tutor prompt 文件存在", tutor.prompt_path.exists(), str(tutor.prompt_path))
    check("tutor 用 summary 记忆", tutor.memory.kind == "summary")
    check("tutor 有预算上限", tutor.budget.max_steps == 20)

    for name in (
        "course.planner",
        "course.researcher",
        "course.tex_writer",
        "course.exercises",
    ):
        spec = get_spec(name)
        check(
            f"{name} prompt 已外置为 md 文件",
            spec.prompt_path is not None and spec.prompt_path.exists(),
            str(spec.prompt_path),
        )

    try:
        get_spec("nonexistent")
        check("未注册 Agent 抛 KeyError", False)
    except KeyError:
        check("未注册 Agent 抛 KeyError", True)


def test_tool_catalog() -> None:
    print("\n── 7.2 工具目录 ──")

    from agents.registry import AGENTS
    from agents.tool_catalog import build_tools, catalog

    cat = catalog()
    check("工具目录含 23 个工具", len(cat) == 23, str(len(cat)))

    # 所有 Agent 声明的工具名都必须在目录中
    missing: List[str] = []
    for name, spec in AGENTS.items():
        for tool_name in spec.tools:
            if tool_name not in cat:
                missing.append(f"{name}:{tool_name}")
    check("Agent 声明的工具名全部可解析", not missing, "; ".join(missing))

    tools = build_tools(
        ("now", "kg_search", "unknown_xxx"), user_id="u1", session_id="s1"
    )
    check("未知工具名跳过而非崩溃", len(tools) == 2, f"构造出 {len(tools)} 个")


def test_domain_events() -> None:
    print("\n── 7.3 业务事件定义 ──")

    from agent_core.runtime.events import DomainEvent
    from agents.events import (
        KIND_FILE_CREATED,
        KIND_MASTERY_UPDATED,
        file_created,
        mastery_updated,
        payload_of,
    )

    ev = file_created("f1", title="卡片", file_type="html_card", index=3)
    check(
        "file_created 构造正确",
        isinstance(ev, DomainEvent) and ev.kind == KIND_FILE_CREATED,
    )
    check("payload 含 index（保序用）", ev.payload["index"] == 3)

    m = mastery_updated("n1", 0.15)
    check("mastery_updated 构造正确", m.payload["delta"] == 0.15)

    check("payload_of 命中", payload_of(m, KIND_MASTERY_UPDATED)["node_id"] == "n1")
    check("payload_of 不命中返回 None", payload_of(m, KIND_FILE_CREATED) is None)

    # 事件必须可 JSON 序列化（要推给前端）
    try:
        json.dumps(ev.to_dict(), ensure_ascii=False)
        check("DomainEvent 可 JSON 序列化", True)
    except (TypeError, ValueError) as e:
        check("DomainEvent 可 JSON 序列化", False, str(e))


def test_interaction_policy() -> None:
    print("\n── 7.4 交互策略（已从 TutorService 拆出）──")

    from services.policy import MODE_CARD, MODE_CHAT, MODE_QUIZ, MODE_VIZ
    from services.policy.interaction import InteractionPolicy

    p = InteractionPolicy()

    cases = [
        ("什么是微积分", {"first_turn": True}, MODE_CARD, "首轮固定卡片"),
        ("考考我", {}, MODE_QUIZ, "练习意图"),
        ("给我一个交互演示", {}, MODE_VIZ, "交互可视化"),
        ("帮我生成卡片", {}, MODE_CARD, "显式要卡片"),
        ("你好", {}, MODE_CHAT, "闲聊"),
        ("为什么", {"recent_card": True}, MODE_CHAT, "卡片后追问"),
        ("嗯", {}, MODE_CHAT, "短输入"),
        ("请详细解释一下量子纠缠的数学推导过程", {}, MODE_CARD, "富内容"),
    ]

    wrong: List[str] = []
    for msg, kw, expect, desc in cases:
        got = p.decide(msg, **kw)
        if got.mode != expect:
            wrong.append(f"{desc}({msg!r}) 期望 {expect} 得到 {got.mode}")
    check("8 个典型场景判定正确", not wrong, "; ".join(wrong))

    d = p.decide("考考我")
    hint = d.render_hint()
    check("建议渲染含模式与依据", "推荐模式" in hint and "判断依据" in hint)
    check("兼容旧字典接口", d.as_dict()["mode"] == MODE_QUIZ)

    # 关键词表可覆盖
    from services.policy.interaction import KeywordTable

    custom = InteractionPolicy(KeywordTable(quiz=("来道题",)))
    check("关键词表可自定义", custom.decide("来道题").mode == MODE_QUIZ)


def test_turn_collector() -> None:
    print("\n── 7.5 TurnCollector 副作用收集 ──")

    from agent_core.runtime.events import DomainEvent
    from services.turn_collector import TurnCollector

    turn = TurnCollector()

    # 卡片（index 2）→ 先到的 quiz（index 0）应排在前面
    ev_card = turn.on_tool_result(
        "generate_html_card", {"title": "卡片A"}, json.dumps({"file_id": "f_card"}), 2
    )
    ev_quiz = turn.on_tool_result(
        "create_quiz", {"question": "1+1=?"}, json.dumps({"quiz_id": "q1"}), 0
    )
    ev_node = turn.on_tool_result(
        "create_node",
        {},
        json.dumps({"created": True, "node_id": "n1", "title": "节点"}),
        1,
    )
    ev_mastery = turn.on_tool_result(
        "update_mastery", {"node_id": "n1", "delta": 0.2}, "ok", 3
    )

    check("卡片产出 DomainEvent", isinstance(ev_card, DomainEvent))
    check("测验产出 DomainEvent", isinstance(ev_quiz, DomainEvent))
    check("节点产出 DomainEvent", isinstance(ev_node, DomainEvent))
    check("掌握度产出 DomainEvent", isinstance(ev_mastery, DomainEvent))

    # 核心：产物按 index 插槽排序，而非按 hook 调用顺序
    check(
        "产物按全局 index 保序（quiz@0 在 card@2 之前）",
        turn.file_ids == ["q1", "f_card"],
        str(turn.file_ids),
    )
    check("节点 ID 收集正确", turn.created_node_ids == ["n1"])
    check("测验 ID 收集正确", turn.created_quiz_ids == ["q1"])
    check("掌握度累加正确", turn.mastery_changes == {"n1": 0.2})
    check("node_refs 排除新建节点", turn.node_refs == [])

    # 错误结果不应产生副作用
    turn2 = TurnCollector()
    check(
        "工具报错不产生事件",
        turn2.on_tool_result("generate_html_card", {}, "Error: 失败", 0) is None,
    )
    check(
        "非法 JSON 不崩溃",
        turn2.on_tool_result("create_node", {}, "not json", 0) is None,
    )
    check(
        "无关工具返回 None",
        turn2.on_tool_result("kg_search", {}, "结果", 0) is None,
    )

    # 消息构造
    msg = turn.build_assistant_message("回复内容")
    check("assistant 消息含产物清单", msg.artifacts.files == ["q1", "f_card"])
    check("产物含掌握度增量", msg.artifacts.mastery_delta == {"n1": 0.2})
    files = turn.session_files(msg.id)
    check("会话文件关联到消息", len(files) == 2 and files[0].from_message_id == msg.id)


async def test_registry_build_agent() -> None:
    print("\n── 7.6 注册表实际装配 Agent ──")

    from agent_core.agent.react import ReActAgent
    from agent_core.llm.base import BaseLLM, LLMResponse, StreamFinishEvent
    from agents.providers import StaticSuffixProvider
    from agents.registry import build_agent

    class FakeLLM(BaseLLM):
        def __init__(self):
            super().__init__(model_name="fake")

        def think(self, messages, tools=None, tool_choice=None, config=None):
            return LLMResponse(content="ok")

        async def async_think(
            self, messages, tools=None, tool_choice=None, config=None
        ):
            return LLMResponse(content="ok")

        async def stream_think(
            self, messages, tools=None, tool_choice=None, config=None
        ):
            yield StreamFinishEvent(response=LLMResponse(content="ok"))

    agent = build_agent(
        "tutor",
        llm=FakeLLM(),
        user_id="u_test",
        session_id="s_test",
        extra_providers=[StaticSuffixProvider("附加上下文")],
    )
    check("装配出 ReActAgent", isinstance(agent, ReActAgent))
    check(
        "工具已注册（数量与声明一致）",
        len(agent.tool_registry.tool_names) >= 14,
        f"{len(agent.tool_registry.tool_names)} 个",
    )
    check(
        "记忆工厂为 SummaryMemory",
        type(agent.memory_factory()).__name__ == "SummaryMemory",
    )

    providers = agent.prompt_builder.providers
    check(
        "provider 含声明的 profile + 追加的 suffix",
        len(providers) == 2,
        str([p.name for p in providers]),
    )


# ======================================================================
# 阶段 8：Workflow + structured_think
# ======================================================================


async def test_workflow_dag() -> None:
    print("\n── 8.1 Workflow DAG 拓扑与并行 ──")

    from agent_core.agent.workflow import (
        MemoryCheckpointStore,
        Node,
        NodeDoneEvent,
        Workflow,
        WorkflowDoneEvent,
    )
    from agent_core.runtime import new_context

    order: List[str] = []

    def make(nid: str, delay: float = 0.0):
        async def _run(inputs, ctx):
            if delay:
                await asyncio.sleep(delay)
            order.append(nid)
            return {"value": nid, "upstream": sorted(k for k in inputs if k != "seed")}

        return _run

    wf = Workflow(
        [
            Node("a", run=make("a")),
            Node("b", run=make("b", 0.02), needs=("a",)),
            Node("c", run=make("c"), needs=("a",)),
            Node("d", run=make("d"), needs=("b", "c")),
        ],
        name="test",
    )

    check("拓扑分层正确", wf.layers == [["a"], ["b", "c"], ["d"]], str(wf.layers))

    ctx = new_context()
    events = [e async for e in wf.stream({"seed": 1}, ctx)]
    done = [e for e in events if isinstance(e, WorkflowDoneEvent)]

    check("工作流完成", len(done) == 1)
    check("拓扑顺序被遵守", order.index("a") == 0 and order.index("d") == 3, str(order))
    check("层内并行（慢的 b 不阻塞 c）", order[1] == "c", str(order))
    check("下游可见上游输出", done[0].outputs["d"]["upstream"] == ["a", "b", "c"])

    node_dones = [e for e in events if isinstance(e, NodeDoneEvent)]
    check("每节点产出完成事件", len(node_dones) == 4)
    check("进度单调递增至 100", node_dones[-1].pct == 100, f"{node_dones[-1].pct}%")

    # 分数权重：节点声明顺序与拓扑序不一致时，pct 仍须收敛到 100
    weights = {
        "a": 0.12,
        "b": 0.18,
        "c": 0.35,
        "d": 0.05,
        "e": 0.1,
        "f": 0.25,
        "g": 0.2,
        "h": 0.45,
        "i": 0.15,
        "j": 0.3,
    }
    wf_w = Workflow(
        [
            Node(nid, run=make(nid), weight=weights[nid])
            for nid in ("e", "g", "j", "i", "f", "d", "c", "h", "a", "b")
        ],
        name="weighted",
    )
    dones_w = [
        e async for e in wf_w.stream({}, new_context()) if isinstance(e, NodeDoneEvent)
    ]
    check("分数权重下进度达 100", dones_w[-1].pct == 100, f"{dones_w[-1].pct}%")

    # 分数权重 + 断点续跑（部分节点来自 checkpoint）同样须收敛到 100
    store_w = MemoryCheckpointStore()
    ctx_w = new_context()
    for nid in ("a", "b", "c", "d"):
        await store_w.save(ctx_w.run_id, nid, {"value": nid})
    dones_r = [
        e async for e in wf_w.stream({}, ctx_w, store_w) if isinstance(e, NodeDoneEvent)
    ]
    check("分数权重续跑进度达 100", dones_r[-1].pct == 100, f"{dones_r[-1].pct}%")

    # 环检测
    try:
        Workflow(
            [
                Node("x", run=make("x"), needs=("y",)),
                Node("y", run=make("y"), needs=("x",)),
            ]
        )
        check("循环依赖被检出", False)
    except ValueError as e:
        check("循环依赖被检出", "循环依赖" in str(e))

    try:
        Workflow([Node("x", run=make("x"), needs=("ghost",))])
        check("未定义依赖被检出", False)
    except ValueError as e:
        check("未定义依赖被检出", "未定义" in str(e))


async def test_workflow_resume() -> None:
    print("\n── 8.2 Workflow 断点续跑 ──")

    from agent_core.agent.workflow import (
        MemoryCheckpointStore,
        Node,
        NodeSkippedEvent,
        Workflow,
        WorkflowAbortedEvent,
    )
    from agent_core.runtime import new_context

    runs: List[str] = []
    fail_switch = {"on": True}

    async def ok_node(inputs, ctx):
        runs.append("first")
        return {"data": "第一步产物"}

    async def flaky_node(inputs, ctx):
        runs.append("second")
        if fail_switch["on"]:
            raise RuntimeError("模拟失败")
        return {"data": "第二步产物", "got": inputs["first"]["data"]}

    wf = Workflow(
        [Node("first", run=ok_node), Node("second", run=flaky_node, needs=("first",))],
        name="resume_test",
    )
    store = MemoryCheckpointStore()
    ctx = new_context()

    # 第一次：second 失败
    events1 = [e async for e in wf.stream({}, ctx, store)]
    aborted = [e for e in events1 if isinstance(e, WorkflowAbortedEvent)]
    check("失败节点导致中止", len(aborted) == 1 and aborted[0].failed_node == "second")
    check("失败前的节点已 checkpoint", "first" in await store.load(ctx.run_id))

    # 第二次：修复后用同一 run_id 续跑
    fail_switch["on"] = False
    runs.clear()
    events2 = [e async for e in wf.stream({}, ctx, store)]

    skipped = [e for e in events2 if isinstance(e, NodeSkippedEvent)]
    check(
        "已完成节点被跳过（不重跑）",
        len(skipped) == 1 and skipped[0].node_id == "first",
    )
    check("续跑只执行未完成节点", runs == ["second"], str(runs))

    outputs = await wf.run({}, ctx, store)
    check("续跑后能读到上游 checkpoint 数据", outputs["second"]["got"] == "第一步产物")


async def test_workflow_optional_and_retry() -> None:
    print("\n── 8.3 Workflow 可选节点与重试 ──")

    from agent_core.agent.workflow import (
        Node,
        NodeFailedEvent,
        Workflow,
        WorkflowDoneEvent,
    )
    from agent_core.runtime import new_context

    attempts = {"n": 0}

    async def retry_node(inputs, ctx):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError(f"第 {attempts['n']} 次失败")
        return {"ok": True}

    async def bad_optional(inputs, ctx):
        raise RuntimeError("可选节点失败")

    async def tail(inputs, ctx):
        return {"saw_optional": inputs.get("opt")}

    wf = Workflow(
        [
            Node("retry", run=retry_node, retries=2),
            Node("opt", run=bad_optional, optional=True, needs=("retry",)),
            Node("tail", run=tail, needs=("opt",)),
        ],
        name="retry_test",
    )

    ctx = new_context()
    events = [e async for e in wf.stream({}, ctx)]
    done = [e for e in events if isinstance(e, WorkflowDoneEvent)]

    check(
        "重试后成功", attempts["n"] == 3 and len(done) == 1, f"重试 {attempts['n']} 次"
    )
    failed = [e for e in events if isinstance(e, NodeFailedEvent)]
    check("可选节点失败被记录", len(failed) == 1 and failed[0].node_id == "opt")
    check("可选节点失败不阻断下游", done[0].outputs["tail"]["saw_optional"] == {})

    # 取消传导
    async def slow(inputs, ctx):
        await asyncio.sleep(0.5)
        return {}

    state = {"n": 0}

    def cancelled():
        state["n"] += 1
        return state["n"] > 1

    from agent_core.agent.workflow import WorkflowAbortedEvent

    wf2 = Workflow([Node("s1", run=slow), Node("s2", run=slow, needs=("s1",))])
    ctx2 = new_context(is_cancelled=cancelled)
    ev2 = [e async for e in wf2.stream({}, ctx2)]
    aborted = [e for e in ev2 if isinstance(e, WorkflowAbortedEvent)]
    check("取消信号中止工作流", len(aborted) == 1 and aborted[0].reason == "cancelled")


async def test_structured_think() -> None:
    print("\n── 8.4 structured_think 统一结构化输出 ──")

    from agent_core.llm.base import BaseLLM, LLMResponse, StreamFinishEvent
    from agent_core.runtime import new_context
    from agent_core.structured import (
        StructuredOutputError,
        extract_json,
        structured_think,
    )

    # 解析能力：覆盖 4 种 LLM 常见输出形态
    cases = [
        ('{"a": 1}', {"a": 1}, "纯 JSON"),
        ('```json\n{"a": 2}\n```', {"a": 2}, "代码围栏"),
        ('好的，结果是：{"a": 3} 希望有帮助', {"a": 3}, "夹在文本中"),
        ('{"tex": "\\to \\text{x}"}', None, "LaTeX 非法转义"),
    ]
    for raw, expect, desc in cases:
        try:
            got = extract_json(raw)
            ok = (got == expect) if expect is not None else isinstance(got, dict)
            check(f"解析 {desc}", ok, str(got)[:60])
        except StructuredOutputError as e:
            check(f"解析 {desc}", False, str(e))

    class Model:
        def __init__(self, name: str = "", count: int = 0):
            self.name = name
            self.count = count

    class ScriptLLM(BaseLLM):
        def __init__(self, outs):
            super().__init__(model_name="s")
            self.outs = outs
            self.calls = 0

        def think(self, messages, tools=None, tool_choice=None, config=None):
            i = min(self.calls, len(self.outs) - 1)
            self.calls += 1
            return LLMResponse(content=self.outs[i], usage={"total_tokens": 10})

        async def async_think(
            self, messages, tools=None, tool_choice=None, config=None
        ):
            return self.think(messages, tools, tool_choice, config)

        async def stream_think(
            self, messages, tools=None, tool_choice=None, config=None
        ):
            yield StreamFinishEvent(response=self.think(messages))

    ctx = new_context()
    obj = await structured_think(
        ScriptLLM(['{"name": "测试", "count": 5}']),
        [{"role": "user", "content": "q"}],
        Model,
        ctx=ctx,
    )
    check("schema 校验并构造对象", obj.name == "测试" and obj.count == 5)
    check("token 计入预算", ctx.budget.tokens == 10, str(ctx.budget.tokens))

    # 首次不合法 → 带错误重试
    llm = ScriptLLM(["不是 JSON", '{"name": "重试成功", "count": 1}'])
    obj2 = await structured_think(
        llm, [{"role": "user", "content": "q"}], Model, ctx=new_context(), retries=1
    )
    check("解析失败后重试成功", obj2.name == "重试成功" and llm.calls == 2)

    # 重试耗尽
    try:
        await structured_think(
            ScriptLLM(["永远不是 JSON"]),
            [{"role": "user", "content": "q"}],
            Model,
            ctx=new_context(),
            retries=1,
        )
        check("重试耗尽抛 StructuredOutputError", False)
    except StructuredOutputError:
        check("重试耗尽抛 StructuredOutputError", True)


# ======================================================================
# 全链路
# ======================================================================


def test_business_imports() -> None:
    print("\n── 9. 业务模块导入与应用装配 ──")

    mods = [
        "services.tutor_service",
        "services.turn_collector",
        "services.policy.interaction",
        "services.workflow_store",
        "services.immersive.layout",
        "services.immersive.agents",
        "services.immersive.service",
        "services.extract_service",
        "agents.registry",
        "agents.tool_catalog",
        "agents.events",
        "agents.providers",
        "agents.chat_agent",
        "routers.sessions",
        "channels.bridge",
        "court.service",
        "court.forge",
    ]

    code = (
        "import warnings; warnings.filterwarnings('ignore');"
        "import importlib, sys; bad=[]\n"
        f"for m in {mods!r}:\n"
        "    try: importlib.import_module(m)\n"
        "    except Exception as e: bad.append(m + ' -> ' + type(e).__name__ + ': ' + str(e)[:120])\n"
        "print('BAD:' + '; '.join(bad) if bad else 'ALL_OK')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    out = proc.stdout.strip().splitlines()
    tail = out[-1] if out else ""
    check(f"{len(mods)} 个业务模块全部可导入", tail == "ALL_OK", tail[:200])

    app_code = (
        "import warnings; warnings.filterwarnings('ignore')\n"
        "from main import app\n"
        "print('ROUTES:', len([r for r in app.routes if hasattr(r, 'methods')]))"
    )
    proc2 = subprocess.run(
        [sys.executable, "-c", app_code],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    routes_line = [
        line for line in proc2.stdout.splitlines() if line.startswith("ROUTES:")
    ]
    count = int(routes_line[0].split()[1]) if routes_line else 0
    check("FastAPI 应用完整装配", count >= 109, f"{count} 个路由")


# ======================================================================
# 入口
# ======================================================================


async def main() -> int:
    print("=" * 70)
    print("阶段 5-8 改造验证")
    print("=" * 70)

    test_no_reverse_dependency()
    test_layout_split()
    await test_context_provider()
    test_settings_injection()
    test_agent_registry()
    test_tool_catalog()
    test_domain_events()
    test_interaction_policy()
    test_turn_collector()
    await test_registry_build_agent()
    await test_workflow_dag()
    await test_workflow_resume()
    await test_workflow_optional_and_retry()
    await test_structured_think()
    test_business_imports()

    print("\n" + "=" * 70)
    if _failures:
        print(f"失败 {len(_failures)} 项：")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
