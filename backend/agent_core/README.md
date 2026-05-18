# agent_core — 通用 Agent 基础库

与业务解耦的通用 Agent 基础库，封装了多种推理范式、工具系统、技能加载、上下文构建与记忆管理等核心抽象，可独立复用到任意 LLM 应用中。

## 定位

定位在 LangChain / AutoGen 与裸写循环之间——**只保留跑通一个工业级 Agent 所必需的抽象**，把扩展点清晰暴露出来。

## 模块结构

```
agent_core/
├── agent/           # 推理范式：ReAct / Reflection / Plan-and-Solve
│   ├── base.py      #   BaseAgent 基类
│   ├── react.py     #   ReAct 循环
│   ├── reflection.py#   Reflection 自我批评
│   └── plan_and_solve.py  # Plan-and-Solve 多步规划
├── tool/            # 工具系统
│   ├── base.py      #   BaseTool 基类 + JSON Schema 校验
│   ├── decorator.py #   @tool 装饰器
│   ├── registry.py  #   ToolRegistry 工具注册表
│   ├── agent_tool.py#   Agent-as-Tool 多 Agent 协作
│   ├── mcp.py       #   MCP 协议工具包装
│   ├── web.py       #   Web 搜索工具（Tavily / arXiv / DuckDuckGo）
│   ├── filesystem.py#   文件系统操作工具
│   ├── shell.py     #   Shell 命令执行工具
│   ├── pdf_compile.py#  LaTeX → PDF 编译工具
│   ├── tts_say.py   #   macOS TTS 语音合成工具
│   └── openai_image_gen.py # 图像生成工具
├── context/         # 上下文构建器
│   ├── base.py      #   BaseContextBuilder 基类
│   ├── simple.py    #   SimpleContextBuilder
│   ├── skill_prompt.py #  SkillPromptBuilder（技能注入）
│   └── profile_skill.py # ProfileSkillBuilder（画像 + 技能）
├── llm/             # LLM 适配层
│   ├── base.py      #   BaseLLM 抽象接口
│   └── openai_llm.py#   OpenAI 兼容实现
├── memory/          # 记忆系统
│   └── profile.py   #   用户画像记忆（Profile Memory）
├── skills/          # 技能加载器
│   └── loader.py    #   Markdown 声明式技能解析与加载
├── builtins/        # 内置技能
│   ├── agent.md     #   Agent 通用行为规范
│   └── skills/      #   内置技能包
│       ├── file_operations/
│       ├── python_repl/
│       ├── tex_beamer_writing/
│       ├── pdf_courseware_orchestration/
│       └── web_search/
└── layout.py        # 目录布局管理
```

## 三种推理范式

所有 Agent 共享同一个基类 `BaseAgent`，通过依赖注入工作：

| 范式 | 循环结构 | 适用场景 |
|------|----------|---------|
| **ReAct** | `think → (tool_call)* → think → ...` 直到无工具调用 | 工具调用主流场景 |
| **Reflection** | `draft → critique → revise` 多轮自我批评 | 内容质量优先的生成任务 |
| **Plan-and-Solve** | `plan → execute(step)* → (replan)? → synthesize` | 长链路多步骤任务 |

三种范式均提供三种调用方式：

```python
# 同步
result = agent.run(messages)

# 异步
result = await agent.async_run(messages)

# 流式（yield 强类型事件）
async for event in agent.async_stream(messages):
    # AgentThinkEvent / AgentToolCallEvent / AgentToolResultEvent / AgentFinalEvent
    ...
```

## 工具系统

三种定义方式，按场景选择：

### 1. `@tool` 装饰器

从函数签名 + docstring 自动生成 Function Calling schema：

```python
from agent_core.tool import tool

@tool
def search_web(query: str, max_results: int = 5) -> str:
    """搜索互联网获取最新信息。

    Args:
        query: 搜索关键词
        max_results: 最大返回结果数
    """
    ...
```

### 2. 继承 `BaseTool`

适合需要依赖注入（DB / user_id）的场景：

```python
from agent_core.tool import BaseTool

class CreateNodeTool(BaseTool):
    name = "create_node"
    description = "创建知识图谱节点"
    parameters = { ... }

    def __init__(self, user_id: int):
        self.user_id = user_id

    def run(self, **kwargs) -> str:
        ...
```

### 3. MCP 协议包装

对接外部 MCP 服务器，支持 stdio / SSE / streamableHttp 三种传输：

```python
from agent_core.tool import MCPToolWrapper

tools = await MCPToolWrapper.from_server("http://localhost:3000/mcp")
```

## Agent-as-Tool：多 Agent 协作

任何 Agent 都可通过 `as_tool()` 包装为工具，注册到父 Agent 的 `ToolRegistry` 中：

```python
orchestrator = PlanAndSolveAgent(
    tool_registry=ToolRegistry([
        researcher.as_tool(name="research",  description="资料检索"),
        writer.as_tool(name="write_tex",  description="撰写 Beamer"),
    ]),
)
```

## Markdown 声明式技能

技能以 `SKILL.md` 形式存放，用 frontmatter 声明依赖与加载策略：

```markdown
---
description: 将 TeX 编译为 PDF
always: false
requires:
  bins: [xelatex, latexmk]
  env:  [BEAMER_TEMPLATE_DIR]
---
# TeX Beamer 撰写规范 ...
```

- 缺依赖的技能自动从可用列表剔除
- `workspace/skills/` 优先于 `builtins/skills/`，用户可覆盖默认行为
- `always: true` 常驻 system prompt，其它按需加载，节省 token

## 用户画像记忆

对话结束后 LLM 自动提取用户信息，跨会话持久化：

```python
from agent_core.memory import ProfileMemory

memory = ProfileMemory(user_id=1)
# 对话结束后自动提取并存储用户偏好、学习风格等
await memory.extract_and_save(conversation)
```
