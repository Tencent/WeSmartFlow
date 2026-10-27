**English | [中文](./README.md)**

# WeSmartFlow Backend

FastAPI-based backend service powering Agent tutoring, knowledge graph management, and content generation for educational scenarios.

## Module Structure

```text
backend/
├── agent_core/             # General-purpose Agent framework
├── agents/                 # Educational Agents, tool registration and prompts
├── agents/tools/           # Cards, visualizations, quizzes and graph tools
├── services/               # Business services, model factories and credit accounting
├── services/immersive/     # Immersive course workflows
├── channels/               # WeClaw messaging and card screenshots
├── kg/                     # Public knowledge graph and Graph RAG
├── routers/                # FastAPI routes
├── repositories/           # Data access
├── models/                 # Request and business data models
├── tests/                  # Regression and browser tests
├── config.py               # Root .env, data and resource paths
├── database.py             # SQLite initialization and connections
├── main.py                 # Service entry point
└── requirements.txt        # Python dependencies
```

## Prerequisites

| Dependency | Purpose |
| --- | --- |
| Python 3.10+ | Backend and Agent runtime |
| Node.js 24+ | Frontend build and ESLint; `environment.yml` currently installs Node.js 25 |
| Frontend development dependencies | The backend visualization validator calls ESLint and reads its configuration |
| Playwright + Chromium | EduViz browser checks and WeClaw card screenshots |
| XeLaTeX, latexmk, SimplePlus Beamer | Optional PDF courseware generation |

## Installation & Launch

**Run the following setup commands from the repository root.** The complete Conda setup is in the [main README](../README_EN.md#-quick-start). For an existing Python environment:

```bash
python -m pip install -r backend/requirements.txt
npm --prefix frontend install --include=dev
python -m playwright install chromium
# First setup only: create the root .env and fill in model and sign-in settings
cp backend/.env.example .env
```

Start the backend in that same Python environment:

```bash
cd backend
python main.py
```

The default port is `8080`; `GET /health` checks service availability. Configuration is loaded from the repository-root `.env`. Optional LaTeX installation commands are in the [main README](../README_EN.md#enable-immersive-pdf-courseware-optional).

## Content generation tools

### HTML cards

`GenerateHtmlCardTool` streams the writer Agent's events, then validates and normalizes the HTML using shared components and CSS. It preserves teaching content and formulas, validates local illustration paths, and archives referenced images. Invalid content gets one revision; incomplete or failed output is not registered as a document. Illustrations are optional and have at most one generation attempt per card.

### EduViz

```text
Design → validate the design structure → generate code
       → static checks → Chromium checks → correctness review
       → register document and return viz_id
```

A structurally valid design proceeds directly to coding. There is no separate design score. Code gets up to three attempts; repair feedback targets concrete problems. A malformed review gets one format retry without regenerating the JavaScript.

| Check | What it does | Effect |
| --- | --- | --- |
| Static | Node.js syntax, ESLint scope analysis, SDK/library rules | Errors block the candidate |
| Browser | Executes the real SDK, samples controls, captures exceptions and checks rendering | Runtime errors, missing output and 900px overflow block the candidate |
| Advisory browser checks | 600px reflow, long content, design/control differences, short probes without observed changes | Recorded as `warnings` |
| Code review | A model inspects concrete functional and teaching errors | `blocking_issues` request repairs; `suggestions` allow publication |

The frontend renders at approximately 900px and scales the iframe as a whole. It does not require the visualization to reflow at 600px. A `light/600px` warning alone therefore does not prevent generation.

**Validation limits:** static rules partly use regular expressions; browser interactions sample SDK setters and compare output rather than testing every mouse/keyboard path. Animation, delayed updates and hidden elements can affect detection. Screenshots are retained for inspection, not automatically reviewed by a vision model. Passing checks does not guarantee correct teaching content or good visual design.

### Streaming and result contracts

Both tools use `async_stream_run`, yielding progress strings and child Agent events. Within tutoring, call them through `ToolRegistry` so tool-result hooks and the shared parent budget remain active. Synchronous `run()` is not supported. Browser checks run asynchronously and terminate their worker on cancellation or timeout.

| Tool | Final successful value | Main artifact |
| --- | --- | --- |
| `generate_html_card` | JSON string `{"file_id":"…","script":""}` | `data/documents/cards/{id}/card.html` |
| `generate_interactive_viz` | `viz_id` string, also the document ID | `data/documents/viz/{id}/viz.js` |

An `Error:` string denotes failure. Progress strings and intermediate `AgentFinalEvent` values are not the tool's final artifact result. The visualization directory also contains `meta.json` (design and quality reports) and `preview.png` (the browser check screenshot).

### Files to extend

| File | Responsibility |
| --- | --- |
| [generate_html_card.py](agents/tools/generate_html_card.py) | Card writer and streaming orchestration |
| [html_card_document.py](agents/tools/html_card_document.py) | HTML normalization, validation and asset archiving |
| [generate_viz.py](agents/tools/generate_viz.py) | Design, code, review and streaming orchestration |
| [viz_quality.py](agents/tools/viz_quality.py) | Design and review data contracts |
| [validate_viz_code.py](agents/tools/validate_viz_code.py) | Static JavaScript validation |
| [viz_runtime.py](agents/tools/viz_runtime.py) / [viz_runtime_worker.py](agents/tools/viz_runtime_worker.py) | Browser process lifecycle and checks |
| [SDK](../frontend/src/components/EduViz/eduviz-sdk.js) / [CORE.md](agents/prompts/skills/eduviz_sdk/CORE.md) | Runtime APIs and model-facing documentation |

## Validation

From the repository root, with the backend Python environment active:

```bash
python -m pip install pytest
python -m pytest backend/tests/test_html_card.py backend/tests/test_viz_quality.py backend/tests/test_viz_streaming.py -q
RUN_VIZ_BROWSER_TESTS=1 python -m pytest backend/tests/test_viz_runtime.py -q
```

These use fixed fixtures and mocked model responses, not paid model calls or production database writes. Browser tests require Chromium. They check known regressions, not the success rate of a live model.

## Troubleshooting

| Symptom | Check or action |
| --- | --- |
| Chromium cannot start / executable missing | Run `python -m playwright install chromium` in the backend environment and under its runtime account; Linux may also need browser system dependencies |
| ESLint or configuration missing | Install `frontend` dependencies with `--include=dev`; retain the SDK, `eslint_assets` configuration and `frontend/node_modules` in the backend deployment |
| `light/600px` overflow | Inspect `warnings`; this is advisory. For a blocking 900px overflow, fix the offending layout |
| Review rejects a candidate | Read `blocking_issues` and the triggering values; optional improvements belong in `suggestions` |
| SDK library or math fails to load | Check access to the SDK's jsDelivr resources; browser dependency failures are separate from code errors |
| Blank visualization or broken controls | Inspect the frontend error, browser diagnostics and, for saved artifacts, `meta.json` and `preview.png` |
| Old behavior after an update | Restart the backend; rebuild/redeploy the frontend if its SDK or sandbox files changed |

## Environment Variables

| Variable | Description | Required | Example |
|----------|-------------|:--------:|---------|
| `LLM_API_KEY` | LLM API key | ✅ | `sk-xxx` |
| `LLM_BASE_URL` | LLM API endpoint | ✅ | `https://api.openai.com/v1` |
| `LLM_MODEL` | Model name | ✅ | `gpt-4o` |
| `BACKEND_HOST` | Listen address. Loopback by default; set `0.0.0.0` explicitly behind a reverse proxy/firewall | No | `127.0.0.1` |
| `BACKEND_PORT` | Listen port | No | `8080` |
| `CORS_ORIGINS` | CORS allowed origins (comma-separated; avoid `*`, a startup warning is emitted) | No | `http://localhost:5173` |
| `JWT_SECRET` | HS256 master key for login tokens, at least 32 random characters; generated when empty | No | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `JWT_SECRET_FILE` | Path of the auto-generated key file (mode 0600) | No | `data/jwt_secret.key` |
| `JWT_EXPIRE_HOURS` | User token lifetime in hours | No | `72` |
| `ADMIN_USERNAME` | Admin console username; all `/api/admin` routes return 503 when unset | No | `admin` |
| `ADMIN_PASSWORD` | Admin console password, preferably 12+ random characters; rotating it revokes existing admin tokens | No | — |
| `ADMIN_TOKEN_EXPIRE_HOURS` | Admin token lifetime in hours | No | `12` |
| `TAVILY_API_KEY` | Web search API | No | `tvly-xxx` |
| `IMG_API_KEY` | Image generation API | No | `sk-xxx` |
| `IMG_BASE_URL` | Image generation endpoint | No | `https://api.openai.com/v1` |
| `IMG_MODEL` | Image generation model | No | `gpt-image-1` |
| `CREDITS_ENFORCEMENT_ENABLED` | Whether wallet balance enforcement is on | No | `true` |
| `GITHUB_CLIENT_ID` | GitHub OAuth client ID | No | — |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth client secret | No | — |
| `SMTP_HOST` | SMTP mail server | No | `smtp.qq.com` |
| `SMTP_PORT` | SMTP port | No | `465` |
| `SMTP_USER` | Sender email | No | — |
| `SMTP_PASSWORD` | SMTP auth code | No | — |
| `WECHAT_MP_APPID` | WeChat Mini Program AppID | No | — |
| `WECHAT_MP_SECRET` | WeChat Mini Program secret | No | — |

### Credit card emails

In Admin → Credit cards → Generate, enable email delivery, search for a user, and choose Generate and send. The recipient address comes from the user's profile; users without an email cannot be selected. The message includes the redemption code, credit amount, and instructions. The recipient still needs to redeem the card.

Use Gift in an existing card's action column to select a recipient and send its code. Gifting preserves the card's amount and redemption limit; it does not create a card, redeem it, or reserve a redemption slot. Disabled, expired, or exhausted cards cannot be gifted, nor can a user receive a gift they have already redeemed. The list shows the latest delivery, while earlier recipient records remain in the database. Retry sends to the latest recipient address.

Delivery reuses `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, and `SMTP_PASSWORD` above. Set `SMTP_FROM_NAME` to customize the sender name. Optionally set `PUBLIC_BASE_URL` to the public website URL to include a settings-page redemption link. Restart the backend after updating; startup creates the delivery-record table automatically.

Admins can inspect delivery status and retry the same code without creating another card. SMTP acceptance does not guarantee inbox delivery. Tasks run within the application process; interrupted tasks show an unknown status after approximately three minutes and can be retried manually after checking the inbox.

## Database

Uses SQLite (WAL mode). The default database is `<repository>/data/wesmartflow.db`, initialized at startup. Setting `ROOT_DIR` changes the database path to `ROOT_DIR/data/wesmartflow.db`; documents live in `data/documents/` and logs in `data/logs/`.

### Connection Management

Uses a **unified short-connection pattern**: all database operations acquire a short-lived connection via `with get_db() as conn`, which auto-commits and closes upon completion, preventing `database is locked` errors from long-held connections.

## API Overview

| Route Prefix | Description |
|-------------|-------------|
| `POST /api/auth/send-code` | Send email verification code |
| `POST /api/auth/verify-code` | Verification code login (auto-registers new users) |
| `POST /api/auth/github` | GitHub OAuth login |
| `POST /api/auth/wechat` | WeChat Mini Program login |
| `GET/POST /api/sessions/...` | Learning session management |
| `POST /api/sessions/{session_id}/chat/stream` | SSE streaming conversation |
| `POST /api/immersive/generate` | Immersive course generation |
| `GET/POST /api/documents/...` | Document management |
| `GET/POST /api/nodes/...` | Knowledge graph nodes |
| `GET/POST /api/quiz/...` | Quiz generation & grading |
| `POST /api/cards/generate-html` | HTML card generation with SSE progress and results |
| `GET /api/documents/{doc_id}/raw` | Main card, visualization or document file |
| `GET /api/documents/{doc_id}/asset/{asset_path}` | Companion assets such as images |
| `POST /api/viz/generate` | Consumes the visualization tool stream and returns JSON `{ok, viz_id, error}` |
| `GET /api/viz/...` | Interactive visualizations |
| `GET /api/brief/...` | Daily brief |
| `GET/PUT /api/settings/...` | System settings |
| `GET /api/usage` | Usage statistics |

## Tech Stack

- **Web Framework**: FastAPI + uvicorn
- **Database**: SQLite (WAL mode)
- **Data Validation**: Pydantic v2
- **LLM**: OpenAI-compatible protocol (supports any compatible gateway)
- **Content Generation**: HTML Knowledge Cards · EduViz Interactive Visualization · XeLaTeX + Beamer (optional)
- **Search**: Tavily / arXiv / DuckDuckGo
- **Image**: OpenAI-compatible image API
- **Document Parsing**: pdfplumber / pdfminer
- **Streaming**: SSE (Server-Sent Events)
- **Authentication**: GitHub OAuth · Email Verification · WeChat Mini Program · JWT


### Promotional credit wallet

One million credits equals CNY 1 of API usage allowance. Every account receives CNY 5 once
on registration. Starting the following calendar month (Asia/Shanghai), up to CNY 1 is added
monthly, only until the balance reaches CNY 5. Balances carry over; missed months are settled
transactionally on the next login, balance lookup or paid call, with the same cap.

Verified GitHub Stars on Tencent/WeSmartFlow earn an additional CNY 5 once per application
account and immutable GitHub ID. This bonus can exceed the monthly top-up cap. Unstarring
and starring again does not earn another reward. Settings includes a verification button;
GitHub OAuth tokens are used for verification and are not stored. OAuth callbacks now require
state validation, including when converting query parameters to hash routes.

Run `conda run -n agent python backend/migrate_credit_wallet.py` for an existing database.
Startup also initializes wallets idempotently. Existing accounts receive CNY 5 once, without
charging historical usage. Legacy monthly quota overrides and FREE_CREDITS_PER_PERIOD
no longer apply. Usage reporting stays separate from the persistent balance. Concurrent
in-flight calls may create a negative balance; future grants offset that balance first.

Tests: `backend/tests/test_credit_wallet.py` and `backend/tests/test_usage_governance.py`.
