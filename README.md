# AscendFlow

**AI 驱动的自适应学习平台**

AscendFlow 是一个全栈智能学习平台，融合多智能体协同与个人知识图谱。平台提供两种互补的学习模式——**交互式辅导**（人机对话）和**沉浸式课程**（全自动课程生成），并通过基于 SM-2 算法的间隔重复知识图谱持续追踪学习者的掌握程度。

---

## 核心功能

### 🎓 交互式辅导（Interactive Tutoring）
- 基于 **ReAct 智能体**，配备 7 个教育领域专用工具，实时引导学习者对话
- 每次讲解自动生成 **Beamer PDF 知识卡片**，含 AI 生成的插图
- 逐页生成 TTS 语音解说，实现有声知识卡片
- 根据学习者水平自适应调整讲解深度，对话中同步构建知识图谱
- 集成 Web 搜索（Tavily / arXiv / WebFetch），获取最新参考资料
- 自动创建知识节点、更新掌握度、生成测验题

### 📚 沉浸式课程生成（Immersive Course）
- 输入一个主题 → 自动生成**多章节图文并茂的 PDF 课件**及配套练习
- 四阶段智能体流水线：**规划器 → 研究者 → TeX 编写器 → 练习生成器**
- 逐页生成 TTS 语音解说（macOS `say`，Tingting 神经网络语音，180 字/分）
- 章节完成后即时流式传输到前端（SSE），无需等待整门课程生成完毕
- 每门课程自动提取知识图谱节点
- 生成的章节 PDF + 音频 + 练习自动打包为 ZIP 资产归档

### 🧠 个人知识图谱（Knowledge Graph）
- 基于 **SM-2 算法**的间隔重复调度（ease_factor / interval / repetitions）
- 节点间支持 **prereq（前置）/ extends（延伸）/ applies（应用）/ contrasts（对比）/ related（相关）** 五种边关系
- 三维掌握度模型：理解度 × 记忆度 × 连接度
- 两种学习模式共享统一的知识图谱
- 可视化图谱探索

### 📊 学习数据分析
- 每日学习热力图与连续打卡计数
- AI 生成的**每日学习计划**与**资讯简报**
- 测验引擎：选择题（single_choice）、填空题（fill_in）、判断题（true_false）、开放题（open_ended）
- 文档管理：上传 PDF/TXT/MD/DOCX（≤50MB），自动提取知识点
- 用户画像记忆，持续积累学习者偏好

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Vue 3 前端  (frontend/)                        │
│                                                                  │
│  Dashboard · Graph · Chat · Quiz · DailyBrief · Documents        │
│  KnowledgeBase · LearningPath · Sessions · Profile · Settings    │
└───────────────────────┬──────────────────────────────────────────┘
                        │  REST + SSE（流式传输）
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI 后端  (backend/)                       │
│                                                                  │
│  TutorService           ImmersiveService       AssetService      │
│  (交互式辅导)            (自动课程生成)          (资产归档)         │
│  ReAct 智能体            PlanAndSolve 智能体    ZIP 打包/归档      │
│  7 个教育工具            4 阶段流水线                              │
│                                                                  │
│  QuizService    DailyPlanService    DailyBriefService            │
│  ExtractService    MemoryService    LLMFactory                   │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │               agent_core  (通用智能体框架)                  │  │
│  │                                                            │  │
│  │  智能体: ReAct · Reflection · PlanAndSolve                 │  │
│  │  工具:   ToolRegistry · @tool 装饰器 · Agent-as-Tool       │  │
│  │          Web搜索 · PDF编译 · 图片生成 · TTS · Shell        │  │
│  │          文件系统 · MCP协议                                 │  │
│  │  技能:   SkillsLoader（常驻/按需加载）                      │  │
│  │  LLM:   OpenAI 兼容                                      │  │
│  │  上下文: Base · Simple · ProfileSkill                      │  │
│  │  记忆:   用户画像记忆（Profile Memory）                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  SQLite（WAL 模式）· 9 张数据表                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
edu-agent/
├── backend/
│   ├── main.py                       # FastAPI 应用入口
│   ├── config.py                     # 配置管理（环境变量）
│   ├── database.py                   # SQLite 数据库（9 张表 + DDL + 连接管理）
│   ├── database_cleanup.py           # 数据库清理工具
│   ├── requirements.txt              # Python 依赖
│   ├── .env.example                  # 环境变量模板
│   │
│   ├── agent_core/                   # ===== 通用智能体框架 =====
│   │   ├── agent/                    #   智能体实现
│   │   │   ├── base.py              #     基础智能体类
│   │   │   ├── react.py             #     ReAct 模式
│   │   │   ├── reflection.py        #     反思模式
│   │   │   └── plan_and_solve.py    #     规划求解模式
│   │   ├── tool/                     #   工具系统
│   │   │   ├── base.py / decorator.py / registry.py
│   │   │   ├── agent_tool.py        #     Agent-as-Tool
│   │   │   ├── web.py               #     Web 搜索（Tavily/arXiv/DDG）
│   │   │   ├── pdf_compile.py       #     LaTeX → PDF 编译
│   │   │   ├── openai_image_gen.py  #     AI 图片生成
│   │   │   ├── tts_say.py           #     TTS 语音合成（macOS say）
│   │   │   ├── shell.py             #     Shell 命令执行
│   │   │   ├── filesystem.py        #     文件系统操作
│   │   │   └── mcp.py               #     MCP 协议支持
│   │   ├── context/                  #   上下文构建器
│   │   │   ├── base.py / simple.py
│   │   │   └── profile_skill.py     #     用户画像 + 技能上下文
│   │   ├── llm/                      #   LLM 适配器
│   │   │   └── openai_llm.py        #     OpenAI 兼容
│   │   ├── memory/                   #   记忆系统
│   │   │   └── profile.py           #     用户画像记忆
│   │   ├── skills/                   #   技能动态加载器
│   │   │   └── loader.py
│   │   ├── layout.py                 #   课程文件布局管理
│   │   └── builtins/skills/          #   内置技能
│   │       ├── file_operations/
│   │       ├── pdf_courseware_orchestration/
│   │       ├── python_repl/
│   │       ├── tex_beamer_writing/
│   │       └── web_search/
│   │
│   ├── agents/                       # ===== 教育领域智能体 =====
│   │   ├── base_agent.py             #   TutorAgent（继承 ReActAgent）
│   │   ├── base_context.py           #   教育上下文构建
│   │   ├── tools/                    #   教育领域工具（7 个）
│   │   │   ├── create_node.py       #     创建知识节点
│   │   │   ├── update_node.py       #     更新节点
│   │   │   ├── get_node.py          #     获取节点信息
│   │   │   ├── search_nodes.py      #     搜索知识节点
│   │   │   ├── update_mastery.py    #     更新掌握度
│   │   │   ├── generate_card.py     #     生成 Beamer PDF 知识卡片
│   │   │   └── create_quiz.py       #     创建测验题
│   │   └── prompts/                  #   提示词与技能定义
│   │       ├── tutor.md             #     导师系统提示词
│   │       ├── extract_enhanced.md  #     增强知识提取提示词
│   │       └── skills/              #     knowledge_card / knowledge_graph / quiz / web_search
│   │
│   ├── services/                     # ===== 业务逻辑层 =====
│   │   ├── tutor_service.py          #   交互式辅导服务
│   │   ├── immersive_service.py      #   沉浸式课程生成服务
│   │   ├── quiz_service.py           #   测验引擎
│   │   ├── extract_service.py        #   知识图谱提取服务
│   │   ├── asset_service.py          #   资产归档（ZIP 打包）
│   │   ├── daily_plan_service.py     #   每日学习计划
│   │   ├── daily_brief_service.py    #   每日资讯简报
│   │   ├── memory_service.py         #   用户画像记忆服务
│   │   └── llm_factory.py            #   LLM 实例工厂
│   │
│   ├── repositories/                 # ===== 数据访问层 =====
│   │   ├── base.py                   #   基础仓库
│   │   ├── user_repo.py
│   │   ├── session_repo.py
│   │   ├── node_repo.py
│   │   ├── document_repo.py
│   │   └── quiz_repo.py
│   │
│   ├── routers/                      # ===== API 路由 =====
│   │   ├── sessions.py               #   会话管理 + SSE 消息流
│   │   ├── nodes.py                  #   知识节点 CRUD
│   │   ├── documents.py              #   文档上传与管理
│   │   ├── quiz_user.py              #   测验 + 用户 + 简报
│   │   ├── immersive.py              #   沉浸式课程
│   │   └── settings.py               #   运行时配置管理
│   │
│   ├── models/                       # ===== Pydantic 数据模型 =====
│   │   ├── user.py / session.py / node.py / document.py / quiz.py
│   │   └── base.py
│   │
│   └── SimplePlus-BeamerTheme/       # LaTeX Beamer 主题（MIT）
│
├── frontend/
│   ├── package.json                  # Vue 3 + Vite 8 + Vue Router 4
│   ├── vite.config.js                # 开发代理 → localhost:8000
│   ├── index.html
│   ├── public/
│   │   ├── favicon.svg / icons.svg
│   │   └── pdf.worker.mjs           # pdfjs-dist worker
│   └── src/
│       ├── App.vue                   # 主布局 + 路由
│       ├── main.js                   # 入口
│       ├── style.css                 # 全局样式
│       ├── views/                    # ===== 页面 =====
│       │   ├── ChatView.vue          #   统一 AI 辅导界面（交互式 + 沉浸式）
│       │   ├── DashboardView.vue    #   学习概览仪表盘
│       │   ├── GraphView.vue         #   知识图谱可视化
│       │   ├── KnowledgeBase.vue    #   知识节点库
│       │   ├── SessionsView.vue     #   学习历史记录
│       │   ├── QuizView.vue          #   测验界面
│       │   ├── DocumentsView.vue    #   文档管理
│       │   ├── DailyBrief.vue       #   每日资讯简报
│       │   ├── LearningPath.vue     #   学习路径
│       │   ├── ProfileView.vue      #   用户档案
│       │   └── SettingsView.vue     #   系统设置
│       ├── api/                      # API 客户端
│       │   ├── base.js              #   Fetch 封装
│       │   ├── sessions.js          #   会话 API（含 SSE）
│       │   ├── nodes.js / documents.js / quizzes.js / user.js
│       │   └── index.js
│       ├── components/               # 通用组件
│       │   └── PageLayout.vue
│       └── composables/
│           └── useTheme.js           # 主题切换
│
├── environment.yml                   # Conda 环境（Python 3.14 + Node 25）
└── data/                             # 运行时数据（已 gitignore）
    ├── ascendflow.db                 #   SQLite 数据库
    ├── generated_cards/              #   辅导生成的 PDF 卡片 + 音频
    ├── assets/                       #   归档资产（pdf/ audio/ files/）
    ├── immersive/                    #   沉浸式课程（courses/ profile/ skills/）
    ├── sessions/                     #   会话消息 JSON 文件
    └── uploads/                      #   上传的文档
```

---

## 快速开始

### 环境依赖

| 依赖项 | 版本要求 | 用途 | 是否必须 |
|--------|---------|------|---------|
| Python | ≥ 3.10（推荐 3.14，与 `environment.yml` 一致） | 后端运行 | ✅ |
| Node.js | ≥ 18（推荐 20+） | 前端构建 | ✅ |
| XeLaTeX + latexmk | TeX Live 2023+ / MacTeX / MiKTeX 均可 | 编译 Beamer 知识卡片与沉浸式课件 | ✅ |
| SimplePlus-BeamerTheme | `master` 分支 | Beamer 课件主题（`\usetheme{SimplePlus}`） | ✅ |
| macOS `say` + Tingting 语音包 | macOS 13+ | TTS 语音解说（非 macOS 可跳过，语音功能将自动禁用） | 可选 |

### 1. 安装 Python

推荐使用 Conda 统一管理 Python 与 Node 版本：

```bash
# macOS：安装 Miniconda（如已有 conda 可跳过）
brew install --cask miniconda

# 创建并激活环境（同时包含 Python + Node，见 environment.yml）
conda env create -f environment.yml
conda activate agent

# 安装后端依赖
pip install -r backend/requirements.txt
```

> 若不使用 Conda，确保系统 Python ≥ 3.10 后，手动执行 `pip install -r backend/requirements.txt` 即可。

### 2. 安装 Node.js 与前端依赖

```bash
# 方式一：Conda 环境已包含 Node（environment.yml 已声明 nodejs）
conda activate agent
node -v   # 确认版本 ≥ 18

# 方式二：使用 nvm 或系统安装
# macOS: brew install node
# Linux: curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash && nvm install 20

# 安装前端依赖
cd frontend
npm install
cd ..
```

### 3. 安装 LaTeX（XeLaTeX + latexmk）

项目使用 **XeLaTeX**（支持中文 + xeCJK）配合 **latexmk** 编译 Beamer 演示文稿。

```bash
# macOS（推荐 MacTeX，体积较大，约 5GB；或较小的 BasicTeX 约 100MB）
brew install --cask mactex-no-gui
# 或轻量方案：
# brew install --cask basictex
# sudo tlmgr update --self && sudo tlmgr install latexmk xetex beamer xecjk

# Ubuntu / Debian
sudo apt-get update
sudo apt-get install -y texlive-xetex texlive-latex-extra texlive-fonts-extra \
                        texlive-lang-chinese latexmk

# Windows
# 安装 MiKTeX（https://miktex.org/）或 TeX Live（https://tug.org/texlive/），
# 并在首次使用时允许按需下载缺失宏包。

# 验证
xelatex --version
latexmk --version
```

### 4. 下载 SimplePlus Beamer 主题

`generate_card`、`tex_beamer_writing` 等组件依赖 `\usetheme{SimplePlus}`，需将主题仓库克隆到 `backend/SimplePlus-BeamerTheme/`（**默认位置，无需额外配置环境变量**）：

```bash
# 在项目根目录执行
git clone https://github.com/pm25/SimplePlus-BeamerTheme.git backend/SimplePlus-BeamerTheme

# 验证目录结构
ls backend/SimplePlus-BeamerTheme/beamerthemeSimplePlus.sty   # 应能看到该文件
```

如需放置到其它路径，可通过环境变量 `BEAMER_TEMPLATE_DIR` 指向绝对路径（详见下方环境变量说明）。

### 5. 配置环境变量

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入下方「环境变量说明」中的必填项
```

### 6. 启动

```bash
# 启动后端（端口 8000）
conda activate agent
cd backend && python main.py

# 启动前端（端口 5173，另开一个终端）
conda activate agent
cd frontend && npm run dev
```

启动成功后浏览器访问 <http://localhost:5173>。

### 环境变量说明

所有变量读取自 `backend/.env`（基于 `backend/.env.example`）。

| 变量名 | 说明 | 是否必填 | 示例 |
|--------|------|---------|------|
| `OPENAI_API_KEY` | OpenAI 兼容 API 密钥 | ✅ | `sk-xxx` |
| `OPENAI_BASE_URL` | LLM API 端点地址 | ✅ | `https://api.openai.com/v1` |
| `LLM_MODEL` | 主对话模型名称 | ✅ | `gpt-4o` |
| `TAVILY_API_KEY` | Tavily 搜索 API 密钥（Web 搜索工具） | Web 搜索需要 | `tvly-xxx` |
| `IMG_API_KEY` | 图像生成 API 密钥 | AI 插图需要 | `sk-xxx` |
| `IMG_BASE_URL` | 图像生成端点地址 | AI 插图需要 | `https://api.openai.com/v1` |
| `IMG_MODEL` | 图像生成模型名称 | AI 插图需要 | `dall-e-3` / `gpt-image-1` |
| `BEAMER_TEMPLATE_DIR` | SimplePlus 主题目录绝对路径（**未设置则使用默认路径 `backend/SimplePlus-BeamerTheme/`**） | 可选 | `/Users/me/themes/SimplePlus-BeamerTheme` |
| `BACKEND_HOST` | 后端监听地址 | 可选（默认 `0.0.0.0`） | `127.0.0.1` |
| `BACKEND_PORT` | 后端端口 | 可选（默认 `8000`） | `8000` |
| `CORS_ORIGINS` | 允许的跨域来源 | 可选（默认 `http://localhost:5173`） | `http://localhost:5173` |

---

## API 设计

```
# 用户
GET    /api/me                    获取用户信息
PATCH  /api/me/config             更新用户配置

# 知识节点
GET    /api/nodes                 所有节点（图谱数据，含 relations）
GET    /api/nodes/:id             节点详情
PATCH  /api/nodes/:id             编辑节点

# 文档
GET    /api/documents             文档列表
POST   /api/documents             上传文档（multipart/form-data，≤50MB）
GET    /api/documents/:id         文档详情
DELETE /api/documents/:id         删除文档

# 会话
GET    /api/sessions              历史会话列表
POST   /api/sessions              创建新会话 { topic, mode }
GET    /api/sessions/:id          会话详情
POST   /api/sessions/:id/message  发送消息（SSE 流式返回）
POST   /api/sessions/:id/finish   结束会话

# 沉浸式课程
POST   /api/immersive/generate    生成课程（SSE 流式）
GET    /api/immersive/courses     课程列表

# 测验
GET    /api/quizzes               习题列表（?node_id=xxx 筛选）
POST   /api/quizzes/generate      AI 生成习题
POST   /api/quizzes/:id/answer    提交答案

# 资讯简报
GET    /api/brief                 获取今日简报

# 系统设置
GET    /api/settings              读取所有配置
PUT    /api/settings              批量更新配置
```

---

## 数据库设计

SQLite 数据库，WAL 模式，包含 9 张数据表：

| 数据表 | 用途 |
|--------|------|
| `users` | 用户信息（偏好设置、用户画像） |
| `sessions` | 学习会话（交互式 + 沉浸式，消息存文件） |
| `nodes` | 知识图谱节点（SM-2 调度参数 + 关系边） |
| `quizzes` | 测验题目及作答记录 |
| `documents` | 文档管理（上传文档 + AI 生成的 PDF） |
| `study_logs` | 学习活动日志（热力图 + 统计数据） |
| `daily_plans` | 每日学习计划缓存（每天一次） |
| `daily_briefs` | 每日资讯简报缓存（每天一次） |
| `settings` | 系统配置 KV 存储（运行时可修改） |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 · Vue Router 4 · Vite 8 · pdfjs-dist · marked · KaTeX · DOMPurify · pdf-lib |
| 后端 | FastAPI · SQLite（WAL）· Pydantic · SSE-Starlette · uvicorn |
| 智能体框架 | agent_core（自研）：ReAct / Reflection / PlanAndSolve |
| LLM 集成 | OpenAI SDK |
| 工具系统 | ToolRegistry · @tool 装饰器 · Agent-as-Tool · MCP 协议 |
| 技能系统 | SkillsLoader（Markdown SKILL.md 声明式技能定义） |
| PDF 生成 | XeLaTeX + latexmk · Beamer SimplePlus 主题 |
| 语音合成 | macOS Say（Tingting 神经网络语音，180 字/分） |
| Web 搜索 | Tavily · arXiv · DuckDuckGo |
| 图片生成 | OpenAI 兼容图片生成 API |
| 文档解析 | pdfplumber · pdfminer |

---

## 许可证

MIT
