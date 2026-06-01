**[English](./README_EN.md) | 中文**

# WeSmartFlow Frontend

基于 Vue 3 的单页应用，提供自适应学习的完整交互界面。

## 模块结构

```
frontend/
├── public/              # 静态资源
│   ├── logo.jpg         #   应用 Logo
│   ├── logo.png         #   浏览器标签图标（圆角处理）
│   └── icons.svg        #   SVG 图标集
├── src/
│   ├── views/           # 页面视图
│   │   ├── LoginView.vue       # 登录页（邮箱 / GitHub / 微信）
│   │   ├── DashboardView.vue   # 今日学习（学习计划 + 热力图）
│   │   ├── ChatView.vue        # AI 辅导（交互式 + 沉浸式）
│   │   ├── GraphView.vue       # 知识图谱可视化
│   │   ├── KnowledgeBase.vue   # 知识库管理
│   │   ├── QuizView.vue        # 测验中心
│   │   ├── DocumentsView.vue   # 文档管理
│   │   ├── SessionsView.vue    # 学习记录
│   │   ├── DailyBrief.vue      # 每日简报
│   │   ├── LearningPath.vue    # 学习路径
│   │   ├── ProfileView.vue     # 个人中心
│   │   └── SettingsView.vue    # 系统设置
│   ├── components/      # 可复用组件
│   │   ├── EduViz/      #   交互式可视化沙盒
│   │   │   ├── EduVizSandbox.vue  # iframe 沙盒渲染器
│   │   │   ├── EduVizDemo.vue     # 可视化演示组件
│   │   │   ├── eduviz-sdk.js      # EduViz SDK 核心库
│   │   │   └── sandboxTemplate.js # 沙盒 HTML 模板
│   │   ├── HtmlCard/    #   HTML 知识卡片渲染
│   │   │   └── HtmlCard.vue       # 安全渲染 Agent 生成的 HTML 卡片
│   │   ├── QuizCard/    #   测验卡片
│   │   │   └── QuizCard.vue       # 多题型测验交互组件
│   │   ├── VizCard/     #   可视化卡片
│   │   │   └── VizCard.vue        # 可视化结果展示卡片
│   │   └── chat/        #   对话辅助组件
│   │       ├── ThinkBlock.vue     # Agent 思考过程展示
│   │       └── ToolCallBlock.vue  # 工具调用过程展示
│   ├── api/             # API 客户端
│   │   ├── base.js      #   基础请求封装（含 Token 管理）
│   │   ├── index.js     #   统一导出
│   │   ├── auth.js      #   认证 API
│   │   ├── sessions.js  #   会话 API（含 SSE 流式）
│   │   ├── documents.js #   文档 API
│   │   ├── nodes.js     #   知识节点 API
│   │   ├── quizzes.js   #   测验 API
│   │   ├── settings.js  #   设置 API
│   │   ├── brief.js     #   简报 API
│   │   └── user.js      #   用户 API
│   ├── composables/     # Vue 组合式函数
│   │   ├── useAuth.js   #   认证状态管理
│   │   └── useTheme.js  #   主题切换
│   ├── styles/          # 全局样式
│   │   └── page-list.css#   列表页通用样式
│   ├── assets/          # 构建时处理的资源
│   ├── App.vue          # 根组件（侧边栏布局）
│   ├── main.js          # 应用入口（路由 + 全局样式）
│   └── style.css        # 全局 CSS 变量与基础样式
├── index.html           # HTML 入口
├── package.json         # 依赖配置
├── vite.config.js       # Vite 构建配置
├── eslint.config.js     # ESLint 配置
└── stylelint.config.cjs # Stylelint 配置
```

## 环境要求

| 依赖    | 版本 | 说明     |
| ------- | ---- | -------- |
| Node.js | ≥ 18 | 运行时   |
| npm     | ≥ 9  | 包管理器 |

## 安装与启动

```bash
# 安装依赖
npm install

# 开发模式（端口 5173）
npm run dev

# 生产构建
npm run build

# 预览生产构建
npm run preview
```

## 核心依赖

| 包         | 版本  | 用途               |
| ---------- | ----- | ------------------ |
| vue        | ^3.5  | UI 框架            |
| vue-router | ^4.6  | 路由管理           |
| marked     | ^18.0 | Markdown 渲染      |
| katex      | ^0.16 | LaTeX 数学公式渲染 |
| dompurify  | ^3.3  | HTML 安全净化      |
| pdfjs-dist | ^5.6  | PDF 文件渲染       |
| pdf-lib    | ^1.17 | PDF 文件操作       |

## 页面功能

| 页面     | 路由         | 功能                                     |
| -------- | ------------ | ---------------------------------------- |
| 登录     | `/login`     | 多方式登录（邮箱验证码 / GitHub / 微信） |
| AI 辅导  | `/chat`      | 交互式对话学习 + 沉浸式课程生成（首页）  |
| 今日学习 | `/dashboard` | 个性化学习计划、学习热力图、待复习节点   |
| 知识图谱 | `/graph`     | 力导向图可视化、节点详情、掌握度展示     |
| 知识库   | `/knowledge` | 知识节点列表管理                         |
| 测验     | `/quiz`      | 多题型测验（单选/填空/判断/开放题）      |
| 文档     | `/documents` | 文档上传与知识抽取                       |
| 学习记录 | `/sessions`  | 历史会话列表                             |
| 每日简报 | `/brief`     | AI 生成的每日学习资讯                    |
| 个人中心 | `/profile`   | 用户画像与学习统计                       |
| 设置     | `/settings`  | LLM 配置、系统设置                       |

## 特性

- **SSE 流式对话** — 实时展示 AI 回复，支持 Markdown + LaTeX + 代码高亮渲染
- **HTML 知识卡片** — 安全渲染 Agent 生成的交互式 HTML 知识卡片（DOMPurify 净化）
- **EduViz 交互式可视化** — iframe 沙盒渲染 Agent 生成的教学可视化（算法演示、参数探索等）
- **测验卡片** — 内嵌式多题型测验，即时反馈与评分
- **沉浸式学习** — 多章节课件渐进式展示，支持音频播放
- **知识图谱可视化** — 力导向图 + 三维掌握度展示
- **Agent 透明度** — 展示 Agent 思考过程与工具调用详情
- **暗色主题** — 支持亮色 / 暗色主题切换
- **离开确认** — 生成中离开页面时弹出确认提示，防止意外中断
- **响应式布局** — 适配桌面端浏览器

## 开发规范

- ESLint + Prettier 代码格式化
- Stylelint CSS 规范检查
- 组件采用 `<script setup>` 组合式 API
- CSS 变量统一管理主题色
