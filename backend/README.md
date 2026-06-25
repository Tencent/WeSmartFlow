**[English](./README_EN.md) | 中文**

# WeSmartFlow Backend

基于 FastAPI 的后端服务，承载教育场景下的 Agent 辅导、知识图谱管理、内容生成等核心业务。

## 模块结构

```
backend/
├── agent_core/          # 通用 Agent 基础库（独立模块，见其 README）
├── agents/              # 教育领域 Agent 与工具
│   ├── chat_agent.py    #   TutorAgent（ReActAgent 子类）
│   ├── tools/           #   教育领域工具
│   │   ├── create_node.py       # 创建知识图谱节点
│   │   ├── update_node.py       # 更新节点信息
│   │   ├── get_node.py          # 获取节点详情
│   │   ├── search_nodes.py      # 搜索知识节点
│   │   ├── update_mastery.py    # 更新掌握度
│   │   ├── generate_card.py     # 生成知识卡片（LaTeX → PDF）
│   │   ├── generate_html_card.py# 生成 HTML 交互式知识卡片
│   │   ├── generate_viz.py      # 生成 EduViz 交互式可视化
│   │   ├── validate_viz_code.py # 可视化代码校验（ESLint）
│   │   ├── viz_registry.py      # 可视化模式注册表
│   │   └── create_quiz.py       # 生成测验题
│   └── prompts/         #   教育 Prompt 与 Skills
│       ├── tutor.md     #     辅导 Agent 系统提示词
│       └── skills/      #     教育领域技能包
├── services/            # 业务服务层
│   ├── tutor_service.py       # AI 辅导服务（SSE 流式对话）
│   ├── quiz_service.py        # 出题与评分服务
│   ├── document_service.py    # 文档上传与管理
│   ├── extract_service.py     # 文档知识抽取
│   ├── memory_service.py      # 用户画像记忆
│   ├── daily_plan_service.py  # 每日学习计划
│   ├── daily_brief_service.py # 每日资讯简报
│   ├── node_service.py        # 知识节点服务
│   ├── asset_service.py       # 静态资源管理
│   ├── user_service.py        # 用户服务
│   ├── quota.py               # 免费额度管理
│   ├── llm_factory.py         # LLM 实例工厂
│   └── immersive/             # 沉浸式学习（多 Agent 流水线）
│       ├── service.py         #   主服务编排
│       ├── agents.py          #   子 Agent 定义
│       ├── persistence.py     #   持久化
│       ├── node_extractor.py  #   知识节点提取
│       ├── profile_updater.py #   用户画像更新
│       ├── suggestions.py     #   学习建议生成
│       ├── exercises.py       #   练习题生成
│       ├── completion.py      #   完成度计算
│       ├── tts.py             #   语音合成
│       ├── sse.py             #   SSE 事件推送
│       └── utils.py           #   工具函数
├── routers/             # FastAPI 路由层
│   ├── auth.py          #   认证（邮箱验证码 / GitHub OAuth / 微信小程序）
│   ├── sessions.py      #   学习会话（SSE 流式对话）
│   ├── immersive.py     #   沉浸式学习
│   ├── documents.py     #   文档管理
│   ├── nodes.py         #   知识图谱节点
│   ├── quiz.py          #   测验
│   ├── cards.py         #   知识卡片（HTML / PDF）
│   ├── viz.py           #   交互式可视化
│   ├── llm.py           #   LLM 配置管理
│   ├── brief.py         #   每日简报
│   ├── settings.py      #   系统设置
│   ├── users.py         #   用户信息
│   └── usage.py         #   用量统计
├── repositories/        # 数据访问层
│   ├── base.py          #   BaseRepository（短连接模式）
│   ├── session_repo.py  #   会话数据
│   ├── node_repo.py     #   知识节点数据
│   ├── quiz_repo.py     #   测验数据
│   ├── document_repo.py #   文档数据
│   ├── user_repo.py     #   用户数据
│   ├── daily_plan_repo.py  # 学习计划数据
│   └── daily_brief_repo.py # 简报数据
├── models/              # Pydantic 数据模型
│   ├── session.py       #   会话模型
│   ├── node.py          #   知识节点模型
│   ├── quiz.py          #   测验模型
│   ├── document.py      #   文档模型
│   └── user.py          #   用户模型
├── database.py          # SQLite 初始化与连接管理
├── config.py            # 配置管理（环境变量）
├── dependencies.py      # FastAPI 依赖注入
├── main.py              # 应用入口
└── requirements.txt     # Python 依赖
```

## 环境要求

| 依赖 | 版本 | 说明 | 必须 |
|------|------|------|:----:|
| Python | ≥ 3.10 | 运行时 | ✅ |
| XeLaTeX + latexmk | TeX Live 2023+ | 编译 Beamer 课件（沉浸模式） | 可选 |
| SimplePlus Beamer 主题 | master | Beamer 课件主题 | 可选 |
| macOS `say` + Tingting | macOS 13+ | TTS 语音（非 macOS 自动降级） | 可选 |

## 安装与启动

```bash
# 安装依赖
pip install -r requirements.txt

# 安装 LaTeX（可选，仅沉浸式课件需要）
brew install --cask mactex-no-gui

# 下载 Beamer 主题（可选）
git clone https://github.com/pm25/SimplePlus-BeamerTheme.git SimplePlus-BeamerTheme

# 配置环境变量（.env 需放在仓库根，同级于 backend/）
cp backend/.env.example .env
# 编辑 .env 填入 API Key 等配置

# 启动服务（默认端口 8080）
python main.py
```

## 环境变量

| 变量 | 说明 | 必填 | 示例 |
|------|------|:----:|------|
| `LLM_API_KEY` | LLM API 密钥 | ✅ | `sk-xxx` |
| `LLM_BASE_URL` | LLM API 端点 | ✅ | `https://api.openai.com/v1` |
| `LLM_MODEL` | 模型名称 | ✅ | `gpt-4o` |
| `BACKEND_HOST` | 监听地址 | 否 | `0.0.0.0` |
| `BACKEND_PORT` | 监听端口 | 否 | `8080` |
| `CORS_ORIGINS` | CORS 允许源 | 否 | `http://localhost:5173` |
| `TAVILY_API_KEY` | Web 搜索 API | 否 | `tvly-xxx` |
| `IMG_API_KEY` | 图像生成 API | 否 | `sk-xxx` |
| `IMG_BASE_URL` | 图像生成端点 | 否 | `https://api.openai.com/v1` |
| `IMG_MODEL` | 图像生成模型 | 否 | `gpt-image-1` |
| `FREE_LLM_TOTAL` | 免费 LLM 调用总次数 | 否 | `100` |
| `FREE_SEARCH_TOTAL` | 免费搜索总次数 | 否 | `30` |
| `FREE_IMAGE_TOTAL` | 免费图片生成总次数 | 否 | `15` |
| `GITHUB_CLIENT_ID` | GitHub OAuth 客户端 ID | 否 | — |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth 客户端密钥 | 否 | — |
| `SMTP_HOST` | SMTP 邮件服务器 | 否 | `smtp.qq.com` |
| `SMTP_PORT` | SMTP 端口 | 否 | `465` |
| `SMTP_USER` | 发件邮箱 | 否 | — |
| `SMTP_PASSWORD` | SMTP 授权码 | 否 | — |
| `WECHAT_MP_APPID` | 微信小程序 AppID | 否 | — |
| `WECHAT_MP_SECRET` | 微信小程序密钥 | 否 | — |

## 数据库

使用 SQLite（WAL 模式），数据库文件自动创建于 `backend/data/` 目录。

### 连接管理

采用**统一短连接模式**：所有数据库操作通过 `with get_db() as conn` 获取短连接，执行完毕自动提交并关闭，避免长时间占用导致 `database is locked`。

## API 概览

| 路由前缀 | 说明 |
|----------|------|
| `POST /api/auth/send-code` | 发送邮箱验证码 |
| `POST /api/auth/verify-code` | 验证码登录（新用户自动注册） |
| `POST /api/auth/github` | GitHub OAuth 登录 |
| `POST /api/auth/wechat` | 微信小程序登录 |
| `GET/POST /api/sessions/...` | 学习会话管理 |
| `POST /api/sessions/{id}/stream` | SSE 流式对话 |
| `POST /api/immersive/generate` | 沉浸式课程生成 |
| `GET/POST /api/documents/...` | 文档管理 |
| `GET/POST /api/nodes/...` | 知识图谱节点 |
| `GET/POST /api/quiz/...` | 测验出题与评分 |
| `GET /api/cards/...` | 知识卡片（HTML / PDF） |
| `GET /api/viz/...` | 交互式可视化 |
| `GET /api/brief/...` | 每日简报 |
| `GET/PUT /api/settings/...` | 系统设置 |
| `GET /api/usage` | 用量统计 |

## 技术栈

- **Web 框架**：FastAPI + uvicorn
- **数据库**：SQLite（WAL 模式）
- **数据验证**：Pydantic v2
- **LLM**：OpenAI 兼容协议（支持任意兼容网关）
- **内容生成**：HTML 知识卡片 · EduViz 交互式可视化 · XeLaTeX + Beamer（可选）
- **搜索**：Tavily / arXiv / DuckDuckGo
- **图像**：OpenAI 兼容图像接口
- **文档解析**：pdfplumber / pdfminer
- **流式推送**：SSE（Server-Sent Events）
- **认证**：GitHub OAuth · 邮箱验证码 · 微信小程序 · JWT
