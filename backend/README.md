**[English](./README_EN.md) | 中文**

# WeSmartFlow Backend

基于 FastAPI 的后端服务，承载教育场景下的 Agent 辅导、知识图谱管理、内容生成等核心业务。

## 模块结构

```text
backend/
├── agent_core/             # 通用 Agent 框架
├── agents/                 # 教育 Agent、工具注册与提示词
├── agents/tools/           # 卡片、可视化、测验与图谱工具
├── services/               # 业务服务、模型工厂与积分治理
├── services/immersive/     # 沉浸式课程工作流
├── channels/               # WeClaw 消息通道及卡片截图
├── kg/                     # 公共知识图谱与 Graph RAG
├── routers/                # FastAPI 路由
├── repositories/           # 数据访问层
├── models/                 # 请求与业务数据模型
├── tests/                  # 回归测试与浏览器用例
├── config.py               # 根目录 .env、数据与资源路径
├── database.py             # SQLite 初始化及连接管理
├── main.py                 # 服务入口
└── requirements.txt        # Python 依赖
```

## 环境要求

| 依赖 | 用途 |
| --- | --- |
| Python 3.10+ | 后端与 Agent 运行时 |
| Node.js 24+ | 前端构建与 ESLint；`environment.yml` 当前安装 Node.js 25 |
| 前端开发依赖 | 后端可视化校验会调用 ESLint 并读取其配置 |
| Playwright + Chromium | EduViz 浏览器检查、WeClaw 卡片截图 |
| XeLaTeX、latexmk、SimplePlus Beamer | 可选，用于 PDF 课件生成 |

## 安装与启动

**以下安装命令均在仓库根目录执行。** 完整 Conda 安装步骤见[主 README](../README.md#-快速开始)。已有 Python 环境可执行：

```bash
python -m pip install -r backend/requirements.txt
npm --prefix frontend install --include=dev
python -m playwright install chromium
# 首次安装时创建根目录 .env，填写模型与登录配置
cp backend/.env.example .env
```

随后在同一 Python 环境启动后端：

```bash
cd backend
python main.py
```

默认端口为 `8080`，`GET /health` 用于检查服务是否可访问。配置从仓库根目录 `.env` 加载。可选的 LaTeX 安装命令见[主 README](../README.md#启用沉浸式-pdf-课件可选)。

## 内容生成工具

### HTML 知识卡片

`GenerateHtmlCardTool` 流式透传卡片撰写 Agent 的事件，再通过统一组件与 CSS 规范化、校验 HTML。处理过程保留教学正文和公式，验证本地插图路径并归档引用的图片。内容不合格时最多修正一次；中断或失败的结果不会登记为文档。插图为可选能力，每张卡片最多尝试生成一次图片。

### EduViz 交互式可视化

```text
设计方案 → 结构校验 → 生成代码
         → 静态检查 → Chromium 检查 → 核心正确性评审
         → 登记文档，返回 viz_id
```

结构有效的方案直接进入实现，不单独进行设计打分。代码最多尝试三轮，反馈针对具体问题修复；评审 JSON 格式不合法时，单独重试一次评审，不要求重写 JavaScript。

| 检查 | 内容 | 处理方式 |
| --- | --- | --- |
| 静态检查 | Node.js 语法、ESLint 作用域、SDK 与库名规则 | 错误阻止当前代码通过 |
| 浏览器检查 | 执行真实 SDK、抽样触发控件、捕获异常、检查画面 | 运行异常、缺少输出、900px 溢出阻止通过 |
| 浏览器提示 | 600px 重排、内容偏高、控件与设计差异、短时未观察到交互变化 | 记录为 `warnings` |
| 代码评审 | 模型核对有具体依据的功能和教学错误 | `blocking_issues` 要求修复；`suggestions` 不阻止发布 |

前端在约 900px 的内部画布上渲染，再整体缩放 iframe，不要求可视化在 600px 下重新布局。因此单独出现 `light/600px` 提示不会阻止生成。

**检查边界：** 静态规则部分使用正则；动态检查抽样调用 SDK 控件方法并比较输出，没有覆盖全部鼠标、键盘操作。动画、延迟更新和隐藏元素可能影响判断。截图用于留存检查结果，目前没有交给视觉模型评审。检查通过不保证教学内容完全正确或画面一定美观。

### 流式调用与返回值

两个工具都通过 `async_stream_run` 输出进度字符串和子 Agent 事件。辅导流程通过 `ToolRegistry` 调用，以保留结果钩子及父级共享预算；同步 `run()` 不受支持。浏览器检查异步执行，取消或超时会终止检查进程。

| 工具名 | 最后的成功返回值 | 主产物 |
| --- | --- | --- |
| `generate_html_card` | JSON 字符串 `{"file_id":"…","script":""}` | `data/documents/cards/{id}/card.html` |
| `generate_interactive_viz` | `viz_id` 字符串，也是文档 ID | `data/documents/viz/{id}/viz.js` |

`Error:` 字符串表示失败。进度文字、中途收到的 `AgentFinalEvent` 都不代表工具已经交付最终产物。可视化目录还包含 `meta.json`（方案和质量报告）及 `preview.png`（浏览器检查截图）。

### 扩展入口

| 文件 | 职责 |
| --- | --- |
| [generate_html_card.py](agents/tools/generate_html_card.py) | 卡片生成与流式编排 |
| [html_card_document.py](agents/tools/html_card_document.py) | HTML 规范化、校验及图片归档 |
| [generate_viz.py](agents/tools/generate_viz.py) | 方案、代码、评审与流式编排 |
| [viz_quality.py](agents/tools/viz_quality.py) | 方案与评审的数据结构 |
| [validate_viz_code.py](agents/tools/validate_viz_code.py) | JavaScript 静态检查 |
| [viz_runtime.py](agents/tools/viz_runtime.py) / [viz_runtime_worker.py](agents/tools/viz_runtime_worker.py) | 浏览器进程管理与运行检查 |
| [SDK](../frontend/src/components/EduViz/eduviz-sdk.js) / [CORE.md](agents/prompts/skills/eduviz_sdk/CORE.md) | 运行时 API 与提供给模型的说明 |

## 验证

在仓库根目录、后端 Python 环境中执行：

```bash
python -m pip install pytest
python -m pytest backend/tests/test_html_card.py backend/tests/test_viz_quality.py backend/tests/test_viz_streaming.py -q
RUN_VIZ_BROWSER_TESTS=1 python -m pytest backend/tests/test_viz_runtime.py -q
```

这些测试使用固定用例和模拟模型响应，不调用付费模型或写入生产数据库。浏览器测试需要 Chromium。它们验证已知回归，不等同于真实模型的生成成功率评测。

## 故障排查

| 现象 | 检查或处理 |
| --- | --- |
| Chromium 启动失败、找不到可执行文件 | 在后端实际使用的 Python 环境、运行账户下执行 `python -m playwright install chromium`；Linux 还可能需要浏览器系统依赖 |
| 缺少 ESLint 或配置 | 用 `--include=dev` 安装前端依赖；后端部署保留 SDK、`eslint_assets` 配置与 `frontend/node_modules` |
| 提示 `light/600px` 溢出 | 查看 `warnings`，此项不阻止生成；900px 溢出属于阻塞问题，应修正对应布局 |
| 评审反复不通过 | 核对 `blocking_issues` 中的具体操作、参数与结果；非必要改进应归入 `suggestions` |
| SDK 库或公式加载失败 | 检查能否访问 SDK 使用的 jsDelivr 资源；区分依赖加载失败与代码错误 |
| 画面空白或控件异常 | 查看前端错误、浏览器诊断；已保存的产物可检查 `meta.json` 与 `preview.png` |
| 更新后仍是旧行为 | 重启后端；SDK 或沙盒前端文件有改动时，重新构建并部署前端 |

## 环境变量

| 变量 | 说明 | 必填 | 示例 |
|------|------|:----:|------|
| `LLM_API_KEY` | LLM API 密钥 | ✅ | `sk-xxx` |
| `LLM_BASE_URL` | LLM API 端点 | ✅ | `https://api.openai.com/v1` |
| `LLM_MODEL` | 模型名称 | ✅ | `gpt-4o` |
| `BACKEND_HOST` | 监听地址。默认只监听回环；对外提供服务时显式改为 `0.0.0.0` 并加反向代理/防火墙 | 否 | `127.0.0.1` |
| `BACKEND_PORT` | 监听端口 | 否 | `8080` |
| `CORS_ORIGINS` | CORS 允许源（逗号分隔；不建议 `*`，启动时会告警） | 否 | `http://localhost:5173` |
| `JWT_SECRET` | 登录 token 的 HS256 主密钥，至少 32 个随机字符；留空则自动生成 | 否 | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `JWT_SECRET_FILE` | 自动生成密钥的保存路径（权限 0600） | 否 | `data/jwt_secret.key` |
| `JWT_EXPIRE_HOURS` | 用户 token 有效期（小时） | 否 | `72` |
| `ADMIN_USERNAME` | 管理后台账号；未配置时所有 `/api/admin` 接口返回 503 | 否 | `admin` |
| `ADMIN_PASSWORD` | 管理后台口令，建议使用 12 位以上随机串；轮换后旧 admin token 立即失效 | 否 | — |
| `ADMIN_TOKEN_EXPIRE_HOURS` | admin token 有效期（小时） | 否 | `12` |
| `TAVILY_API_KEY` | Web 搜索 API | 否 | `tvly-xxx` |
| `IMG_API_KEY` | 图像生成 API | 否 | `sk-xxx` |
| `IMG_BASE_URL` | 图像生成端点 | 否 | `https://api.openai.com/v1` |
| `IMG_MODEL` | 图像生成模型 | 否 | `gpt-image-1` |
| `CREDITS_ENFORCEMENT_ENABLED` | 是否启用 credits 拦截 | 否 | `true` |
| `GITHUB_CLIENT_ID` | GitHub OAuth 客户端 ID | 否 | — |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth 客户端密钥 | 否 | — |
| `SMTP_HOST` | SMTP 邮件服务器 | 否 | `smtp.qq.com` |
| `SMTP_PORT` | SMTP 端口 | 否 | `465` |
| `SMTP_USER` | 发件邮箱 | 否 | — |
| `SMTP_PASSWORD` | SMTP 授权码 | 否 | — |
| `WECHAT_MP_APPID` | 微信小程序 AppID | 否 | — |
| `WECHAT_MP_SECRET` | 微信小程序密钥 | 否 | — |

### 积分卡邮件发送

在管理后台「积分卡 → 生成积分卡」中勾选「生成后发送到用户邮箱」，搜索并选择用户后点击「生成并发送邮件」。收件地址取自用户资料，没有邮箱的用户不可选择。邮件包含兑换码、积分额度和兑换说明；用户收到后仍需自行兑换。

已有兑换码可通过列表操作栏的「赠送」选择用户并发送。赠送沿用原卡的额度及兑换人数上限，不新增卡片、不自动兑换或预留名额。已停用、过期、兑完的卡及已兑换过该卡的收件人不能赠送。列表展示最近一次发送，变更收件人前的发送记录会保存在数据库中；「重发邮件」会发给最近一次的收件邮箱。

邮件发送复用上述 `SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASSWORD` 配置，`SMTP_FROM_NAME` 可设置发件人名称。可选设置 `PUBLIC_BASE_URL` 为网站公开访问地址，以便邮件提供设置页兑换链接。更新后重启后端，启动时会自动创建发送记录表。

后台可查看发送状态，失败时重发同一兑换码，不会生成新卡。「已提交邮件服务器」表示 SMTP 服务已接受邮件，不代表已进入收件箱。发送任务在应用进程内执行；服务重启等导致任务中断时，约 3 分钟后显示状态不明，可检查收件箱后手动重发。

## 数据库

使用 SQLite（WAL 模式），默认数据库为仓库根目录的 `data/wesmartflow.db`，由启动初始化创建。设置 `ROOT_DIR` 后，数据库路径为 `ROOT_DIR/data/wesmartflow.db`；文档位于 `data/documents/`，日志位于 `data/logs/`。

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
| `POST /api/sessions/{session_id}/chat/stream` | SSE 流式对话 |
| `POST /api/immersive/generate` | 沉浸式课程生成 |
| `GET/POST /api/documents/...` | 文档管理 |
| `GET/POST /api/nodes/...` | 知识图谱节点 |
| `GET/POST /api/quiz/...` | 测验出题与评分 |
| `POST /api/cards/generate-html` | HTML 卡片生成，SSE 进度与结果 |
| `GET /api/documents/{doc_id}/raw` | 卡片、可视化等文档主文件 |
| `GET /api/documents/{doc_id}/asset/{asset_path}` | 文档伴生图片等资源 |
| `POST /api/viz/generate` | 异步消费可视化工具流，返回 JSON `{ok, viz_id, error}` |
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


### Credits 计价与调用治理

`1,000,000 credits = 1 元人民币`。价格表位于 `services/pricing.py`，快照日期
为 2026-09-06，不会自动同步供应商调价；活动赠额、套餐折扣不自动抵扣。
来源：[DeepSeek](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、
[百炼](https://help.aliyun.com/zh/model-studio/model-pricing)、
[Tavily](https://docs.tavily.com/documentation/api-credits)。

- LLM 按输入、缓存命中、输出 token 分别计算，思考 token 已含在输出中，不重复累加。
  DeepSeek V4 区分北京时间工作日高峰/空闲价格；Qwen Plus 区分长上下文阶梯和思考模式。
  当前表默认百炼北京地域，其他地域、转售服务及合同价应显式覆盖。
- 图像按型号及生成张数计算，已支持 Qwen Image 系列；图像工厂识别北京/新加坡端点。
- 音频按型号及供应商返回的计费字符数计算；没有返回时使用输入字符数估算。本地 say、浏览器语音为零成本。
- Tavily 按 API credit 计量，basic 为 1、advanced 为 2，优先取供应商 usage；默认按 PAYG 价格。
  AnySearch 默认对应官方免费计划，商业合同应配置单价。
- LLM 未返回 usage 时记录 `estimated=1` 的 token 估算，不能还原隐藏思考成本。
  未知 LLM 型号使用日志提示的默认估算价；未知图片/语音型号在调用前拒绝，需先补价格。
  供应商生成媒体成功后即记账，后续下载失败不退掉已产生的成本。

配置（价格覆盖均使用人民币；LLM 单位为元/百万 token，图像为元/张，音频为元/字符，搜索为元/API credit）：

```dotenv
CREDITS_ENFORCEMENT_ENABLED=true
PRICING_USD_CNY=7.2
TAVILY_USD_PER_CREDIT=0.008
# 按实际合同配置，不要把示例数值当作第三方实时价格：
# PRICING_OVERRIDES_JSON={"llm:private-model":{"in":1,"in_cached":0.1,"out":4},"image:private-image":0.2,"audio:private-tts":0.00008,"search:anysearch":0}
```

用量入口与归属：

| 入口 | 治理方式 |
| --- | --- |
| 辅导、出题、卡片、可视化、学习计划、设置测试 | LLM / 图像 / TTS / 搜索工厂按登录用户拦截、记账 |
| 沉浸式课程及并行 researcher、SmartSearch | 同上；补齐 Tavily、AnySearch 调用 |
| 魔法英语小镇、化学实验室、数学花园 | 示例 API 验证 JWT，LLM 工厂归属当前用户 |
| 知识之境 | 原始 HTTP 的 LLM、图片、搜索、两条 TTS 路径逐次检查和记录，后台线程继承用户上下文 |
| 历史示例 / court | JWT 用户归属；后台生成及嵌套线程继承上下文，LLM、图片、CosyVoice 均记录 |
| BingeMate | 当前为静态素材，无付费 API；浏览器播放不扣 credits |
| 审核、画像、知识维护与 embedding | 系统成本单独记录，不占用户额度；embedding 以独立类别入账并经 Provider Gateway 观测 |

示例构建统一注入 `frontend/public/example-auth.js`，只向同源 `/api/` 发送登录凭证。
示例 AI 功能需要先在主应用登录；匿名请求不再记到 `default` 或系统账户。
直接发供应商 HTTP 的示例使用平台凭证，始终占平台额度；用户在设置中添加个人 Key
不会让这些仍使用平台 Key 的调用免费。工厂使用个人 Key 时只记明细，不占平台额度。
`usage_details` 保存单价版本、供应商、地域、单位数、估算标记和额度归属。
历史流水不重新计价，旧明细没有可靠 Key 归属，不能追溯精确拆分。

升级已有数据库：`conda run -n agent python backend/migrate_credits.py`（幂等、只新增表）。
启动时 `init_db()` 也会建表。重启后端加载新的默认开关和价格配置；前端执行 `npm run build`
以同步示例登录脚本。验证：`conda run -n agent python backend/tests/test_usage_governance.py`。

额度控制采用逐次调用前检查余额，供应商返回后记账扣减；并发请求或已经发出的请求可能超额，
这不是原子预扣款系统。已有 Tutor 运行预算继续生效；其他多步任务在下一次付费调用前拦截。


### 积分赠送与余额（取代每月重置配额）

规则集中在 `services/credit_wallet.py`，所有金额用整数 credits 存储：

| 来源 | 金额与规则 |
| --- | --- |
| 注册 | 邮箱、GitHub、微信注册均赠送 5,000,000 credits（5 元），每个应用账户一次 |
| 月度补充 | 从注册/迁移次月起，按北京时间自然月，每月 `max(0, min(1,000,000, 5,000,000 - balance))` |
| GitHub Star | 绑定 GitHub 的用户验证已 Star `Tencent/WeSmartFlow` 后，额外赠送 5,000,000 credits；应用账户和 GitHub 数字 ID 都只可领一次 |

5 元上限仅限制月度补充。注册后领取 Star 奖励可有 10 元余额；不清空、不截断、不按月重置。
取消 Star 不追回已发奖励，重新 Star 不重复发。个人 Key 的调用不扣平台余额，系统任务单独记账。
月度补充在登录、查询余额或付费调用时事务内结算，长期未访问会逐月补齐至上限，
不依赖定时任务；注册当月不额外赠送 1 元。并发已发出的调用可造成负余额，后续赠送先抵扣超额消费。

新增数据表：

- `credit_wallets`：账户余额、已结算月份。
- `credit_transactions`：注册、月度、Star 赠送及消费流水；唯一业务键防止重复入账。
- `github_oauth_states`：10 分钟有效、一次性的 OAuth state，不保存 GitHub access token。

消费流水与原 `usage_events`、`usage_summary` 在同一个数据库事务中写入。
历史消费仍供月度统计，旧 `credit_quotas` 保留但不再生效，`FREE_CREDITS_PER_PERIOD` 不再使用。
`/api/usage/credits/quota` 现在返回 `balance`、`remaining`、当月 `used`、赠送规则、奖励状态及最近收支记录。

GitHub 登录会自动验证 Star；邮箱用户可在设置页点击“绑定 GitHub 并领取”，已绑定用户点击“验证并领取”。
两者均通过已登录的奖励授权入口发起，OAuth state 固定发起用户；绑定不依赖邮箱相同，
不会创建或切换应用账户。GitHub 已绑定其他账户、当前账户已绑定不同 GitHub 时拒绝绑定。
授权流程验证前后端 state、过期和重放；领取流程校验授权的 GitHub ID 与当前账户绑定 ID 一致。
GitHub 未 Star、限流或网络失败不发奖，保留重试机会。
前端 `main.js` 的 OAuth query → hash 跳转必须同时保留 `code` 和 `state`。

迁移已有数据库（只初始化没有钱包的用户，每人 5 元，不追扣历史用量）：

```bash
conda run -n agent python backend/migrate_credit_wallet.py
```

启动时 `init_db()` 也执行幂等初始化。更新后需同步后端及前端构建，旧页面发起的无 state OAuth
回调需刷新页面后重新授权。

离线验证：

```bash
conda run -n agent python backend/tests/test_credit_wallet.py
conda run -n agent python backend/tests/test_usage_governance.py
conda run -n agent node --test frontend/tests/github-reward.test.mjs
```
