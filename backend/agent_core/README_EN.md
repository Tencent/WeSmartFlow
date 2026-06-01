**English | [中文](./README.md)**

# agent_core — General-purpose Agent Core Library

A business-agnostic, general-purpose Agent core library that encapsulates reasoning paradigms, tool systems, skill loading, context building, and memory management — independently reusable in any LLM application.

## Positioning

Sits between LangChain / AutoGen and writing raw loops — **retains only the abstractions essential for running a production-grade Agent**, with extension points clearly exposed.

## Module Structure

```
agent_core/
├── agent/           # Reasoning paradigms: ReAct / Reflection / Plan-and-Solve
│   ├── base.py      #   BaseAgent base class
│   ├── react.py     #   ReAct loop
│   ├── reflection.py#   Reflection self-critique
│   └── plan_and_solve.py  # Plan-and-Solve multi-step planning
├── tool/            # Tool system
│   ├── base.py      #   BaseTool base class + JSON Schema validation
│   ├── decorator.py #   @tool decorator
│   ├── registry.py  #   ToolRegistry tool registry
│   ├── agent_tool.py#   Agent-as-Tool multi-Agent collaboration
│   ├── mcp.py       #   MCP protocol tool wrapper
│   ├── web.py       #   Web search tools (Tavily / arXiv / DuckDuckGo)
│   ├── filesystem.py#   Filesystem operation tools
│   ├── shell.py     #   Shell command execution tool
│   ├── pdf_compile.py#  LaTeX → PDF compilation tool
│   ├── tts_say.py   #   macOS TTS text-to-speech tool
│   └── openai_image_gen.py # Image generation tool
├── context/         # Context builders
│   ├── base.py      #   BaseContextBuilder base class
│   ├── simple.py    #   SimpleContextBuilder
│   ├── skill_prompt.py #  SkillPromptBuilder (skill injection)
│   └── profile_skill.py # ProfileSkillBuilder (profile + skills)
├── llm/             # LLM adapter layer
│   ├── base.py      #   BaseLLM abstract interface
│   └── openai_llm.py#   OpenAI-compatible implementation (supports any compatible gateway)
├── memory/          # Memory system
│   └── profile.py   #   User profile memory (Profile Memory)
├── skills/          # Skill loader
│   └── loader.py    #   Markdown declarative skill parsing & loading
├── builtins/        # Built-in skills
│   ├── agent.md     #   Agent general behavior specification
│   └── skills/      #   Built-in skill packs
│       ├── file_operations/
│       ├── python_repl/
│       ├── tex_beamer_writing/
│       ├── pdf_courseware_orchestration/
│       └── web_search/
└── layout.py        # Directory layout management
```

## Three Reasoning Paradigms

All Agents share the same base class `BaseAgent` and work through dependency injection:

| Paradigm | Loop Structure | Use Case |
|----------|---------------|----------|
| **ReAct** | `think → (tool_call)* → think → ...` until no tool calls | Mainstream tool-calling scenarios |
| **Reflection** | `draft → critique → revise` multi-round self-critique | Generation tasks where content quality is paramount |
| **Plan-and-Solve** | `plan → execute(step)* → (replan)? → synthesize` | Long-chain multi-step tasks |

All three paradigms provide three invocation modes:

```python
# Synchronous
result = agent.run(messages)

# Asynchronous
result = await agent.async_run(messages)

# Streaming (yields strongly-typed events)
async for event in agent.async_stream(messages):
    # AgentThinkEvent / AgentToolCallEvent / AgentToolResultEvent / AgentFinalEvent
    ...
```

## Tool System

Three definition approaches — choose based on your scenario:

### 1. `@tool` Decorator

Auto-generates Function Calling schema from function signature + docstring:

```python
from agent_core.tool import tool

@tool
def search_web(query: str, max_results: int = 5) -> str:
    """Search the internet for the latest information.

    Args:
        query: Search keywords
        max_results: Maximum number of results to return
    """
    ...
```

### 2. Inherit `BaseTool`

Suitable for scenarios requiring dependency injection (DB / user_id):

```python
from agent_core.tool import BaseTool

class CreateNodeTool(BaseTool):
    name = "create_node"
    description = "Create a knowledge graph node"
    parameters = { ... }

    def __init__(self, user_id: int):
        self.user_id = user_id

    def run(self, **kwargs) -> str:
        ...
```

### 3. MCP Protocol Wrapper

Connect to external MCP servers, supporting stdio / SSE / streamableHttp transports:

```python
from agent_core.tool import MCPToolWrapper

tools = await MCPToolWrapper.from_server("http://localhost:3000/mcp")
```

## Agent-as-Tool: Multi-Agent Collaboration

Any Agent can be wrapped as a tool via `as_tool()` and registered in a parent Agent's `ToolRegistry`:

```python
orchestrator = PlanAndSolveAgent(
    tool_registry=ToolRegistry([
        researcher.as_tool(name="research",  description="Research & retrieval"),
        writer.as_tool(name="write_tex",  description="Write Beamer slides"),
    ]),
)
```

## Markdown Declarative Skills

Skills are stored as `SKILL.md` files, with frontmatter declaring dependencies and loading strategies:

```markdown
---
description: Compile TeX to PDF
always: false
requires:
  bins: [xelatex, latexmk]
  env:  [BEAMER_TEMPLATE_DIR]
---
# TeX Beamer Writing Guidelines ...
```

- Skills with missing dependencies are automatically excluded from the available list
- `workspace/skills/` takes priority over `builtins/skills/` — users can override default behavior
- `always: true` skills persist in the system prompt; others are loaded on demand to save tokens

## LLM Adapter Layer

Built on the `BaseLLM` abstract interface, with a built-in OpenAI-compatible implementation supporting:

- **Streaming Output** — `async_stream_chat` returns tokens incrementally
- **Function Calling** — Automatic tool call parsing
- **Multi-model Switching** — Switch between models via configuration
- **Custom Adapters** — Inherit `BaseLLM` to connect any LLM service

```python
from agent_core.llm import OpenAILLM

llm = OpenAILLM(
    api_key="sk-xxx",
    base_url="https://api.openai.com/v1",
    model="gpt-4o"
)
```

## User Profile Memory

After conversations end, the LLM automatically extracts user information, persisted across sessions:

```python
from agent_core.memory import ProfileMemory

memory = ProfileMemory(user_id=1)
# Automatically extracts and stores user preferences, learning styles, etc. after conversation
await memory.extract_and_save(conversation)
```
