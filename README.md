<div align="center">

# WeSmartFlow

**让 AI 陪你理解、尝试、记住，也陪你走进知识发生的现场。**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Vue 3](https://img.shields.io/badge/Vue-3-4FC08D?style=flat-square&logo=vue.js&logoColor=white)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](./LICENSE)

WeSmartFlow 是一个开源的 Agent-native 自适应学习框架。<br/>
它会理解学习目标、组织学习路径、陪你练习，并把每一次进步留在个人知识大脑里。

[在线体验](http://wesmartflow.cn) · [探索模式](#3-主题探索走进一个为知识设计的世界) · [快速开始](#-快速开始) · [发布课程](#发布你的课程) · [English](./README_EN.md)

**🎁 使用 GitHub 或邮箱注册即赠 500 万积分，[为项目点亮 Star](https://github.com/Tencent/WeSmartFlow) 并完成验证，再领 500 万积分**

</div>

---

## 📮 Updates

> 这里会长期记录 WeSmartFlow 的重要变化，并按时间倒序持续更新。

### 2026.08.31 · 免费体验计划开启

使用 **GitHub 或邮箱注册**，即可获得 **500 万免费积分**，用于体验自由辅导、沉浸课程、知识大脑与探索模式。为 WeSmartFlow 的 [GitHub 仓库点亮 Star](https://github.com/Tencent/WeSmartFlow)，并使用绑定的 GitHub 账号完成验证后，还可额外领取 **500 万积分**，合计 **1000 万积分**；每个用户账号及 GitHub 账号仅可领取一次 Star 奖励。

次月起，每月补充最多 **100 万积分**，补至 **500 万积分**余额；余额达到或超过 500 万时不再补充。实际可用时间会随所选模型、学习频率和单次内容长度有所不同。

**领取方式：** 前往 [wesmartflow.cn](http://wesmartflow.cn) 注册并登录，获得注册积分 → [点亮 Star](https://github.com/Tencent/WeSmartFlow) → 在设置页的「我的积分」中点击「绑定 GitHub 并领取」或「验证并领取」，完成验证后获得额外奖励。

### 2026.08 · 探索模式升级：学习不再只发生在聊天框里

我们重新设计了 **探索模式**。

现在，你可以从英语、科学、数学和历史出发，进入拥有角色、规则与任务的学习世界。连续故事、地图探索、实验模拟、动手游戏、历史推演、声音与动画，都可以成为课程的一部分。[查看探索主题](#3-主题探索走进一个为知识设计的世界)。

## 🌱 为什么做 WeSmartFlow

真正的学习，很少是一问一答。

它有好奇、卡住、试错和遗忘，也有某个瞬间突然想通。一个好的学习伙伴，会知道你已经理解了什么、哪里仍然模糊、下一步适合做什么，以及哪些知识需要在以后重新遇见。

WeSmartFlow 围绕这段过程提供五种能力：

- **理解目标**：知道你想学什么，也关注你现在走到了哪里
- **陪伴练习**：用讲解、追问、卡片、可视化和测验帮助你真正动手
- **记住成长**：把概念、联系和掌握变化沉淀进个人知识大脑
- **调整路径**：根据对话与练习反馈，决定接下来该深入、换一种讲法，还是安排复习
- **进入情境**：把知识放进故事、实验和真实任务里，在参与中建立理解

## 🎒 现在你可以怎样学习

### 1. 自由辅导：从一个问题开始

你可以从一个问题开始。Agent 会根据需要生成知识卡片、交互式演示和小测验，也会把新理解记录进知识大脑。

<p align="center">
  <img src="assets/learn.png" width="28%" alt="选择学习模式" />
  <img src="assets/card.png" width="28%" alt="AI 生成知识卡片" />
  <img src="assets/viz.png" width="28%" alt="AI 生成交互式可视化" />
</p>

### 2. 沉浸课程：把一个主题学完整

输入一个想深入理解的主题，多个 Agent 会协作完成资料研究、章节规划、课件、插图、语音和练习。你可以沿着课程大纲学习，也可以随时停下来追问。

<p align="center">
  <img src="assets/大纲.png" width="28%" alt="沉浸课程大纲" />
  <img src="assets/课件.png" width="28%" alt="沉浸课程课件" />
  <img src="assets/交互式可视化.png" width="28%" alt="课程中的交互式可视化" />
</p>

### 3. 主题探索：走进一个为知识设计的世界

在探索页选择感兴趣的主题，通过角色对话、世界探索、自由实验、动手游戏或历史推演来学习。每个主题都可以有自己的画面、声音、角色、地图和进度规则：课程设计者决定这个世界如何运转，WeSmartFlow 负责让它被发现、被打开，并在需要时提供 Agent 与后端能力。

#### 已上线主题

| 主题 | 体验方式 |
|------|----------|
| **魔法英语小镇** | 和 Agent 角色用英语交谈，在找线索、交朋友和创作故事中自然开口 |
| **走进数学花园** | 搭积木、看三视图、发射算式炮弹，在动手中建立空间感与代数直觉 |
| **追剧搭子 BingeMate** | 跟着真实剧情理解表达、文化梗、连读和吞音 |
| **化学实验室** | 自由组合物质与反应条件，让 Agent 现场判断结果并解释原因 |
| **知识之境** | 回到科学知识诞生的现场，与科学家对话并重做经典实验 |
| **生成世界 · 历史** | 让一段历史变成会争论、可质询、能推演的鲜活世界 |

这 6 个主题只是开始。探索页也向老师、开发者和内容创作者开放：你可以发布自己的课程，保留自己的设计和技术选择，也可以和社区一起把一个想法慢慢做成真正好用的学习体验。

#### 示例：魔法英语小镇

**魔法英语小镇**面向 8–16 岁学习者。孩子可以用语音或键盘与角色交流，在寻找小狗、筹备月光节等故事任务中练习询问、描述和邀请。Agent 负责理解表达与生成角色回应，本地状态机负责地点、任务、奖励和通关条件。

### 4. 知识大脑：看见自己正在形成的理解

每一次学习都会留下痕迹。知识大脑把学过的概念沉淀成会生长的知识粒子，记录概念之间的关系、当前掌握度和下一次复习时间，帮助你回顾已经走过的路。

<p align="center">
  <img src="assets/知识大脑.webp" width="60%" alt="个人知识大脑与概念掌握详情" />
</p>

## 🧠 核心能力

### ReAct Agent 个性化辅导

辅导 Agent 会在对话中按需使用教育工具，不同任务由对应工具完成：

| 能力 | 作用 |
|------|------|
| 知识节点创建与更新 | 识别新概念，补充描述、标签和概念关系 |
| 掌握度更新 | 根据学习表现调整对应知识节点的掌握度 |
| HTML 知识卡片 | 把重点整理成易读、可保存的学习卡片 |
| EduViz 交互式可视化 | 用动画、参数和可操作对象解释抽象概念 |
| 即时测验 | 生成单选、填空、判断和开放题，并给出反馈 |
| 图谱检索 | 找回已经学过的内容，避免每次从零开始 |
| 多源搜索 | 通过 Tavily、arXiv 和 DuckDuckGo 补充资料 |
| 语音讲解 | 在支持的环境中生成音频讲解 |

### Graph Memory 个人知识大脑

- **掌握度记录**：用 `mastery_level` 持续记录每个知识节点的掌握变化
- **四类知识关系**：prerequisite / related / extends / contrasts
- **间隔重复**：使用 SM-2 参数安排复习节奏
- **跨场景共享**：自由辅导与沉浸课程使用同一张个人图谱
- **用户画像记忆**：从长期互动中积累学习偏好与背景信息

### Multi-Agent 课程生成

```text
一个学习主题
  │
  ├── 规划 Agent  ── 拆解章节与学习路径
  ├── 研究 Agent  ── 搜集并整理资料
  ├── 撰写 Agent  ── 生成章节课件
  ├── 插图 Agent  ── 生成配图
  ├── 语音 Agent  ── 生成音频讲解
  └── 出题 Agent  ── 配套练习与反馈
  │
  └── PDF + 音频 + 练习 + 知识大脑节点
```

### HTML 知识卡片与 EduViz

**HTML 卡片**适合整理一个知识点：公式、对比、解题步骤或插图。**EduViz**适合通过操作来理解概念：改变参数、逐步执行算法、观察运动或状态变化。

两类工具都会在辅导对话中持续展示生成进度，成功后登记为文档，并可关联知识节点。HTML 卡片使用统一的排版组件；EduViz 基于 SDK 生成 JavaScript，经过检查后按具体问题修复。浏览器检查用于发现运行问题，模型评审用于核对核心正确性；检查通过不等于视觉效果或教学内容已经得到全面验证。

实现方式、依赖、检查规则与故障排查见[后端指南](./backend/README.md#内容生成工具)。

### WeClaw 微信助手接入

> 把学习助手接入微信，随时随地对话学习。

将 edu-agent 作为一个消息通道接入 **WeClaw（微信 clawbridge）**，让微信里的对话直接由你的 AI 学习助手回复：

- **扫码绑定** — 网页端「微信助手」页扫码，将你的微信 bot 与账号绑定（每个用户绑定自己的 bot）
- **多租户长轮询** — 每个 bot 一个 async httpx 长轮询协程（≈ 一条 idle 长连接，而非线程），由 ChannelManager 统一调度，单机可承载大量在线 bot
- **复用对话大脑** — 微信消息直接走 `TutorService`，与网页端共享同一套 ReAct 辅导能力、知识大脑与用户画像
- **卡片转图片** — HTML 知识卡片 / 交互式可视化 / 测验卡片用无头浏览器（Playwright）渲染成图片发送，并附网页端交互链接

## 🛠️ 给开发者

WeSmartFlow 同时是一套可复用的教育 Agent 工程框架。仓库把通用 Agent 能力、教育业务服务、前端应用和独立学习体验分开组织：

<p align="center">
  <img src="assets/architecture/sketch-zh.svg" width="70%" alt="WeSmartFlow 架构：多端学习入口、教育业务服务、agent_core、独立管理的个人学习记忆与公共知识图谱，以及存储和模型工具接入" />
</p>

| 层级 | 路径 | 你可以在这里做什么 |
|------|------|--------------------|
| Agent 基础库 | [`backend/agent_core/`](./backend/agent_core/) | 复用 ReAct、DAG 工作流、工具与 MCP、技能、上下文装配、会话记忆和运行预算 |
| 后端服务 | [`backend/`](./backend/) | 扩展 FastAPI 路由、教育 Agent、知识图谱和沉浸课程工作流 |
| 前端应用 | [`frontend/`](./frontend/) | 开发聊天、课程、图谱、测验与探索门户 |
| 探索主题 | [`examples/`](./examples/) | 用任意前端技术构建独立学习世界，并接入主站 |
| 微信入口 | [`miniprogram/`](./miniprogram/) · [`backend/channels/`](./backend/channels/) | 开发原生小程序与 WeClaw 消息通道，复用后端学习服务 |
| 公共知识图谱 | [`backend/kg/`](./backend/kg/) | 通过 `kg_facade` 接入 Graph RAG、观察记录与提议审核，与个人学习状态分开管理 |

### 把一个新学习世界接入探索模式

探索主题与主站保持轻耦合，可以使用 Vue、React、Svelte、Canvas、Three.js 或原生 HTML 独立开发。你可以做一节完整课程，也可以先发布一个小实验、一段互动故事或一种新的教学玩法。

主站与主题之间只有三类稳定契约：

```text
内容契约：examples/explore-catalog.json
构建契约：build:wesmartflow + 约定的环境变量
服务契约：同源静态路径 + 可选的相对 /api 路径
```

接入一个新主题通常只需要：

1. 在 `examples/` 下创建独立应用；
2. 提供 `build:wesmartflow` 构建命令；
3. 在 `examples/explore-catalog.json` 登记分类、入口和介绍内容；
4. 运行目录校验和构建检查。

```bash
cd frontend
npm run validate:examples
npm run build:examples -- --only your-topic-id
```

完整的字段、路径与构建约定见 [探索主题开发指南](./examples/README.md)。

### 发布你的课程

探索页向每一位愿意认真做课程的人开放。

课程的选题、年龄段、页面风格和互动方式都不设统一模板。你可以从现有主题继续创作，也可以带来一个全新的世界。准备好后，在 `explore-catalog.json` 登记课程并提交 Pull Request；我们会一起检查构建、入口、基本可用性和学习体验，再把它放进探索页。

作者信息会跟随课程展示。课程作者保留自己的代码结构、设计语言和后续内容更新方式。

## 🚀 快速开始

### 环境要求

推荐直接使用仓库中的 Conda 环境，它会准备 Python、Node.js 和后端依赖。

生成沉浸式 PDF 课件时，还需要 XeLaTeX、`latexmk` 与 [SimplePlus Beamer 主题](https://github.com/pm25/SimplePlus-BeamerTheme)。

### 1. 克隆项目

请先安装 Git 和 Git LFS。仓库通过 [Git LFS 规则](./.gitattributes) 管理 PNG、MP4 等资源，`git lfs pull` 用于拉取实际文件内容。

```bash
git lfs install
git clone https://github.com/Tencent/WeSmartFlow.git
cd WeSmartFlow
git lfs pull
```

### 2. 安装依赖

```bash
conda env create -f environment.yml
conda activate agent

npm --prefix frontend install --include=dev

# EduViz 浏览器检查、WeClaw 卡片截图需要浏览器内核
python -m playwright install chromium

# 目前有两个探索主题使用 Vite，需要各自安装一次依赖
npm --prefix examples/Magic_English_Town install
npm --prefix examples/chemastry_lab install
```

如果不使用 Conda，请准备 Python 3.10+ 与Node.js 24+（Conda 环境当前使用 Node.js 25），并手动安装 `backend/requirements.txt`。

### 3. 配置模型与登录方式

```bash
cp backend/.env.example .env
```

编辑仓库根目录的 `.env`。运行学习 Agent 至少需要：

```bash
LLM_API_KEY="your-api-key"
LLM_BASE_URL="https://your-openai-compatible-endpoint/v1"
LLM_MODEL="your-model"
```

OpenAI、DeepSeek、通义千问等 OpenAI 兼容接口均可接入。登录还需要配置 GitHub OAuth、邮箱 SMTP 或微信小程序中的至少一种方式；搜索、图片生成与语音能力可以按需开启。完整变量说明见 [`backend/.env.example`](./backend/.env.example) 和 [后端文档](./backend/README.md)。

安全相关默认值：

- `JWT_SECRET` 留空时，后端会生成随机主密钥并保存到 `data/jwt_secret.key`（权限 0600）；生产环境建议在 `.env` 显式配置随机串，并备份该文件。历史示例值（如 `change-me-in-production`）会导致启动失败。
- 后端默认只监听 `127.0.0.1`。需要局域网/公网访问时显式设置 `BACKEND_HOST=0.0.0.0`，并确保前面有反向代理/防火墙。
- 管理后台需显式配置 `ADMIN_USERNAME` / `ADMIN_PASSWORD`；未配置时所有 `/api/admin` 接口返回 503。

### 4. 启动前后端

```bash
# 终端一：后端，默认端口 8080
cd backend
python main.py
```

```bash
# 终端二：前端，默认端口 5173
cd frontend
npm run dev
```

打开 `http://localhost:5173`。后端健康检查地址为 `http://localhost:8080/health`，探索页位于 `http://localhost:5173/#/explore`。

后端默认关闭代码热重载，避免沉浸课程和交互示例在生成中被 WatchFiles 重启打断。本地开发需要热重载时，显式使用：

```bash
WESMARTFLOW_RELOAD=true python main.py
```

> `npm run dev` 会先构建 `explore-catalog.json` 中登记的本地探索主题。新增主题时，探索页组件可以保持不变。

### 启用 WeClaw 微信助手（可选）

把学习助手接入微信，需要额外几步：

**1. 确认后端 Python 环境已安装 Chromium**

```bash
python -m playwright install chromium
```

**2. 配置环境变量**（仓库根目录 `.env`）

```bash
WECLAW_ENABLED=true                 # 开启 WeClaw 通道
PUBLIC_BASE_URL=https://你的域名     # 对外可访问地址，用于拼卡片/讲义链接
# WECLAW_RENDER_CARDS=true          # 卡片渲染成图片（默认开）
```

**3. 扫码绑定**

重启后端后，登录网页端进入 **「微信助手」** 页 → 点「开始绑定」→ 用微信扫码。绑定成功后，该微信 bot 收到的消息就会由你的 AI 学习助手回复。

| 变量 | 说明 | 默认 |
|------|------|------|
| `WECLAW_ENABLED` | 是否启用 WeClaw 通道 | `false` |
| `PUBLIC_BASE_URL` | 对外基础 URL（卡片/讲义链接） | 空 |
| `WECLAW_RENDER_CARDS` | 卡片渲染成图片发送 | `true` |
| `WECLAW_RENDER_WIDTH` | 截图视口宽度(px) | `480` |

> 说明：HTML 卡片 / 可视化 / 测验会被渲染成图片发送，并附网页端交互链接；PDF 讲义以链接形式发送。

### 启用沉浸式 PDF 课件（可选）

```bash
# macOS
brew install --cask mactex-no-gui

# Ubuntu / Debian
sudo apt install texlive-xetex texlive-latex-extra texlive-fonts-extra \
                 texlive-lang-chinese latexmk

git clone https://github.com/pm25/SimplePlus-BeamerTheme.git backend/SimplePlus-BeamerTheme
```

## 开发文档与验证

| 文档 | 内容 |
| --- | --- |
| [后端指南](./backend/README.md) | 安装、API 协议、内容生成、质量检查与故障排查 |
| [前端指南](./frontend/README.md) | 构建命令、页面路由、流式展示与 iframe 渲染 |
| [Agent 基础库](./backend/agent_core/README.md) | ReAct、工具注册、上下文与运行预算 |
| [探索主题指南](./examples/README.md) | 主题目录、独立应用与接入构建 |

在仓库根目录、已安装依赖的 Python 和 Node 环境中执行：

```bash
# 安装测试依赖
python -m pip install pytest
# 固定用例，不调用付费模型
python -m pytest backend/tests/test_html_card.py backend/tests/test_viz_quality.py backend/tests/test_viz_streaming.py -q
# 需要 Chromium，实际验证渲染和交互
RUN_VIZ_BROWSER_TESTS=1 python -m pytest backend/tests/test_viz_runtime.py -q
# 校验探索主题目录
npm --prefix frontend run validate:examples
```

后端生成 EduViz 时会读取前端 SDK，并调用 ESLint；部署时需要保留这些源文件和前端开发依赖。浏览器缺失、校验失败及渲染问题的处理见[后端故障排查](./backend/README.md#故障排查)。

## 🧩 项目结构

```text
WeSmartFlow/
├── backend/
│   ├── agent_core/          # 通用 Agent 基础库
│   ├── agents/              # 教育 Agent、工具与提示词
│   ├── services/            # 辅导、课程、知识图谱等业务服务
│   ├── channels/            # WeClaw 微信通道（扫码登录 / 长轮询 / 卡片渲染）
│   ├── routers/             # FastAPI 路由与探索主题 API 适配
│   ├── repositories/        # 数据访问层
│   ├── models/              # 数据模型
│   └── main.py              # 后端入口
├── frontend/
│   ├── src/views/           # Chat / Immersive / Graph / Quiz / Explore
│   ├── src/components/      # 卡片、测验、EduViz 等组件
│   └── public/              # 构建后的探索主题产物
├── examples/
│   ├── explore-catalog.json # 探索页内容与构建目录
│   ├── build.mjs            # 统一构建编排
│   └── */                   # 各自独立的互动学习主题
├── environment.yml
└── README.md
```

## 🔧 技术实现与工程方向

WeSmartFlow 优先选择容易理解、方便替换的技术组合。通用能力沉到 `agent_core`，教育场景放在服务层，探索课程保持独立构建；模型、搜索、图像和消息通道都通过清晰的接口接入。

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 · Vue Router · Vite · Three.js · KaTeX · pdf.js |
| 后端 | FastAPI · SQLite（WAL）· sqlite-vec · Pydantic · Uvicorn |
| Agent | 自研 `agent_core` · ReAct · DAG 工作流 · Tool Use · Agent-as-Tool · MCP |
| 模型 | OpenAI 兼容协议，可接入不同模型与网关 |
| 内容 | HTML 知识卡片 · EduViz · XeLaTeX / Beamer · TTS |
| 消息通道 | WeClaw 微信接入（clawbridge 长轮询 · async httpx 协程池 · Playwright 卡片渲染） |
| 搜索 | Tavily · arXiv · DuckDuckGo |
| 认证 | GitHub OAuth · 邮箱验证码 · 微信小程序 · JWT |

工程演进主要围绕三条主线展开：用教育任务评测、Reflection 和链路追踪提高结果的可靠性；通过 MCP 工具生态、多模型路由、多 Agent 并行与分层记忆扩展能力边界；完善 PostgreSQL、对象存储、向量检索和容器化部署，让项目能够承载更稳定的长期服务。相关能力会沿用现有的分层边界，按成熟度逐步进入主干。

## 🤝 一起建设

WeSmartFlow 还在快速生长。我们尤其期待有人带着自己的课程来：一段互动故事、一场科学实验、一座数学花园，甚至一种我们还没见过的学习方式，都可以成为探索页里的下一个入口。

如果你想改进 Agent、接入一种工具，或者只是讲讲真实使用时哪里不顺手，也欢迎提交 Issue 或 Pull Request。准备发布课程时，可以先阅读 [探索主题开发指南](./examples/README.md)；它会告诉你如何保留主题的独立性，同时自然地接入 WeSmartFlow。

## 📄 许可证

本项目基于 [MIT License](./LICENSE) 开源。
