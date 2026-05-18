<div align="center">

# WeSmartFlow

**面向教育场景的 Agent-native 自适应学习框架**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Vue 3](https://img.shields.io/badge/Vue-3-4FC08D?style=flat-square&logo=vue.js&logoColor=white)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](./LICENSE)

探索 AI Agent 如何从通用问答深入真实学习过程——<br/>
承担知识诊断、学习路径规划、个性化辅导、内容生成、测验反馈和长期记忆演化。

[项目介绍](#-项目介绍) · [功能展示](#-功能展示) · [核心能力](#-核心能力) · [快速开始](#-快速开始) · [项目结构](#-项目结构) · [路线图](#-路线图)

</div>

---

## 📌 项目介绍

**WeSmartFlow** 是一套面向教育场景的 Agent-native 自适应学习框架，旨在探索 AI Agent 如何从简单问答进一步深入真实学习过程。

### 为什么不是又一个 AI 学习助手？

大量 AI 学习类项目仍停留在"聊天助手"或"内容生成器"阶段——本质是 Chatbot + Prompt，主要能力是回答问题或生成学习材料。它们缺少对**学习过程本身**的建模，也缺少对学习状态、知识结构和反馈闭环的持续追踪。

WeSmartFlow 的核心价值不在于对大模型进行简单封装，而在于提供一套面向教育场景的 **Agent 工程框架**。它将 ReAct、Reflection、Graph Memory、Tool Use、Multi-Agent Collaboration 等能力结合起来，使 Agent 能够：

- **理解学习目标** — 不只是回答问题，而是理解学习者当前处于什么阶段
- **追踪学习状态** — 通过知识图谱持续记录掌握程度、概念关系和复习节奏
- **沉淀知识资产** — 将学习行为转化为可持续演化的结构化资产
- **在反馈中调整** — 根据测验结果和学习表现持续优化学习策略

## 📱 功能展示

### 📊 今日学习 — 个性化学习计划与热力图

<img src="assets/dashboard.png" width="640" />

### 💬 AI 辅导 — 开始学习

<img src="assets/learning.png" width="640" />

### 💬 AI 辅导 — 交互式学习，实时生成学习卡片，更新知识图谱

<img src="assets/interactivelearning.png" width="640" />

### 💬 AI 辅导 — 沉浸式学习，一次性生成学习资料，添加知识节点

<img src="assets/immersivelearning.png" width="640" />

### 🕸️ 知识图谱 — 节点详情与掌握度

<img src="assets/node_graph_selectone.png" width="640" />

## 🎯 核心能力

### 一、ReAct Agent 个性化辅导

> Agent 的输出不只是文本回复，而是会**真实改变学习者的长期知识状态**。

辅导 Agent 基于 ReAct 模式，在推理过程中自主调用教育工具：

| 工具能力 | 说明 |
|---------|------|
| 知识节点创建 | 识别新概念，自动创建图谱节点并建立关联 |
| 掌握度更新 | 根据对话表现实时更新三维掌握度（理解 × 记忆 × 连接） |
| 知识卡片生成 | XeLaTeX + Beamer 编译精美 PDF 知识卡片 |
| 测验题生成 | 4 种题型（单选 / 填空 / 判断 / 开放题）即时出题 |
| 图谱检索 | 搜索已有知识节点，避免重复并建立连接 |
| Web 搜索 | Tavily / arXiv / DuckDuckGo 多源搜索补充资料 |
| 语音讲解 | macOS TTS 生成音频讲解 |

### 二、Graph Memory 个人知识图谱

> 学习过程具备**长期记忆和持续优化能力**，而不是每次对话从零开始。

- **三维掌握度模型** — 理解（comprehension）× 记忆（retention）× 连接（connection）
- **五种边关系** — prerequisite / related / part_of / leads_to / contrasts
- **SM-2 间隔重复** — 基于 `ease_factor` / `interval` / `repetitions` 的智能复习调度
- **跨场景共享** — 交互式辅导与沉浸式课程共享同一张图谱
- **用户画像记忆** — 对话结束后 LLM 自动提取用户信息，跨会话持久化

### 三、Multi-Agent Workflow 学习内容生成

> 从学习主题到完整课件包的**全自动编排**。

```
输入：一个学习主题
  │
  ├── 📋 规划 Agent → 拆解为多章节大纲
  ├── 🔍 研究 Agent → 每章节独立搜索资料
  ├── ✍️ 撰写 Agent → 生成 Beamer LaTeX 课件
  ├── 🖼️ 插图 Agent → AI 生成配图
  ├── 🔊 语音 Agent → TTS 生成音频讲解
  └── 📝 出题 Agent → 每章节配套练习
  │
输出：多章节 PDF + 音频 + 练习 + 图谱节点
```

## 🏗️ 架构设计

<img src="assets/framework.png" width="480" />

本仓库包含三层，各层有独立的 README 文档：

| 层级 | 路径 | 说明 | 文档 |
|------|------|------|------|
| Agent 基础库 | `backend/agent_core/` | 通用 Agent 框架，可独立复用 | [README](./backend/agent_core/README.md) |
| 后端服务 | `backend/` | FastAPI 业务服务 | [README](./backend/README.md) |
| 前端应用 | `frontend/` | Vue 3 单页应用 | [README](./frontend/README.md) |

## 🚀 快速开始

### 环境要求

| 依赖 | 版本 | 说明 | 必须 |
|------|------|------|:----:|
| [Python](https://www.python.org/) | ≥ 3.10 | 后端运行时 | ✅ |
| [Node.js](https://nodejs.org/) | ≥ 18 | 前端构建 | ✅ |
| [XeLaTeX + latexmk](https://tug.org/texlive/) | TeX Live 2023+ | 编译 Beamer 知识卡片与课件 | ✅ |
| [SimplePlus Beamer 主题](https://github.com/pm25/SimplePlus-BeamerTheme) | master | Beamer 课件主题 | ✅ |
| macOS `say` + Tingting | macOS 13+ | TTS 语音讲解（非 macOS 自动降级） | 可选 |

你还需要一个 **OpenAI 兼容 API Key**（OpenAI / DeepSeek / 通义千问等均可）。

### 安装与启动

**1. 克隆仓库并安装依赖**

```bash
git clone https://github.com/your-org/WeSmartFlow.git
cd WeSmartFlow

# 推荐使用 Conda 统一管理
conda env create -f environment.yml && conda activate agent

# 安装后端依赖
pip install -r backend/requirements.txt

# 安装前端依赖
cd frontend && npm install && cd ..
```

**2. 安装 LaTeX**

```bash
# macOS
brew install --cask mactex-no-gui

# Ubuntu / Debian
sudo apt install texlive-xetex texlive-latex-extra texlive-fonts-extra \
                 texlive-lang-chinese latexmk

# 验证
xelatex --version && latexmk --version
```

**3. 下载 Beamer 主题**

```bash
git clone https://github.com/pm25/SimplePlus-BeamerTheme.git backend/SimplePlus-BeamerTheme
```

**4. 配置环境变量**

```bash
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，至少填写：

| 变量 | 说明 | 必填 |
|------|------|:----:|
| `OPENAI_API_KEY` | LLM API 密钥 | ✅ |
| `OPENAI_BASE_URL` | LLM API 端点 | ✅ |
| `LLM_MODEL` | 模型名称 | ✅ |
| `TAVILY_API_KEY` | Web 搜索 API | 可选 |
| `IMG_API_KEY` | 图像生成 API | 可选 |

> 完整环境变量说明见 [后端 README](./backend/README.md#环境变量)

**5. 启动服务**

```bash
# 后端（端口 8080）
cd backend && python main.py

# 前端（端口 5173，另开终端）
cd frontend && npm run dev
```

启动成功后浏览器访问 **http://localhost:5173** 即可使用。

## 🧩 项目结构

```
WeSmartFlow/
├── backend/
│   ├── agent_core/          # 通用 Agent 基础库（可独立复用）
│   │   ├── agent/           #   推理范式：ReAct / Reflection / Plan-and-Solve
│   │   ├── tool/            #   工具系统：@tool / BaseTool / MCP / Agent-as-Tool
│   │   ├── skills/          #   Markdown 声明式技能加载器
│   │   ├── context/         #   上下文构建器
│   │   ├── memory/          #   用户画像记忆
│   │   ├── llm/             #   LLM 适配层
│   │   └── builtins/        #   内置技能与工具
│   ├── agents/              # 教育领域 Agent 与工具
│   ├── services/            # 业务服务层
│   ├── routers/             # FastAPI 路由
│   ├── repositories/        # 数据访问层
│   ├── models/              # Pydantic 数据模型
│   └── main.py              # 应用入口
├── frontend/
│   ├── src/
│   │   ├── views/           # 页面视图
│   │   ├── api/             # API 客户端（含 SSE）
│   │   └── composables/     # Vue 组合式函数
│   └── package.json
├── environment.yml          # Conda 环境定义
└── README.md                # 本文件（产品文档）
```

## 🗺️ 路线图

| 状态 | 方向 | 说明 |
|:----:|------|------|
| 🎯 | **Agent Benchmark** | 围绕教育任务建设评测体系 |
| 🎯 | **Reflection 反馈调整** | 围绕学习表现和测验结果进行反思 |
| 🎯 | **更多推理范式** | Tree-of-Thought · LATS · 自定义范式 |
| 🎯 | **多 Agent 并行** | `as_tool()` 并行 fan-out + reduce |
| 🔜 | **MCP 工具接入** | 外部题库、知识库的标准化接入 |
| 🔜 | **向量记忆** | 引入向量存储实现语义检索式记忆 |
| 🔜 | **三层记忆** | 短期 → 中期 → 长期 |
| 🔜 | **可观测性** | Agent 执行链路追踪 · token 用量仪表盘 |
| 🔜 | **多模型路由** | 按任务复杂度自动选择模型 |
| 📋 | **生产级存储** | PostgreSQL · S3 · 向量数据库 |
| 📋 | **容器化部署** | Docker Compose · K8s |

## 🔧 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 · Vue Router 4 · Vite 8 · pdfjs-dist · marked · KaTeX · pdf-lib |
| 后端 | FastAPI · SQLite（WAL）· SSE-Starlette · Pydantic · uvicorn |
| Agent 基础库 | `agent_core` 自研 · ReAct / Reflection / Plan-and-Solve · `@tool` · Agent-as-Tool · MCP |
| LLM | OpenAI 兼容协议（可替换为任意兼容网关） |
| 内容生成 | XeLaTeX + Beamer (SimplePlus) · macOS `say` (Tingting) |
| 搜索 | Tavily · arXiv · DuckDuckGo |
| 图像 | OpenAI 兼容图像接口 |
| 文档解析 | pdfplumber · pdfminer |

## 📄 许可证

本项目基于 [MIT](./LICENSE) 协议发布。
