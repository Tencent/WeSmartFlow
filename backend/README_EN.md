**English | [中文](./README.md)**

# WeSmartFlow Backend

FastAPI-based backend service powering Agent tutoring, knowledge graph management, and content generation for educational scenarios.

## Module Structure

```
backend/
├── agent_core/          # General-purpose Agent core library (standalone module, see its README)
├── agents/              # Education-domain Agents & tools
│   ├── chat_agent.py    #   TutorAgent (ReActAgent subclass)
│   ├── tools/           #   7 education-domain tools
│   │   ├── create_node.py    # Create knowledge graph node
│   │   ├── update_node.py    # Update node information
│   │   ├── get_node.py       # Get node details
│   │   ├── search_nodes.py   # Search knowledge nodes
│   │   ├── update_mastery.py # Update mastery level
│   │   ├── generate_card.py  # Generate knowledge card (LaTeX → PDF)
│   │   └── create_quiz.py    # Generate quiz questions
│   └── prompts/         #   Education prompts & skills
│       ├── tutor.md     #     Tutor Agent system prompt
│       └── skills/      #     Education skill packs
├── services/            # Business service layer
│   ├── tutor_service.py       # AI tutoring service (SSE streaming)
│   ├── quiz_service.py        # Quiz generation & grading
│   ├── document_service.py    # Document upload & management
│   ├── extract_service.py     # Document knowledge extraction
│   ├── memory_service.py      # User profile memory
│   ├── daily_plan_service.py  # Daily study plan
│   ├── daily_brief_service.py # Daily news brief
│   ├── node_service.py        # Knowledge node service
│   ├── asset_service.py       # Static asset management
│   ├── user_service.py        # User service
│   ├── quota.py               # Free quota management
│   ├── llm_factory.py         # LLM instance factory
│   └── immersive/             # Immersive learning (multi-Agent pipeline)
│       ├── service.py         #   Main service orchestration
│       ├── agents.py          #   Sub-Agent definitions
│       ├── persistence.py     #   Persistence
│       ├── node_extractor.py  #   Knowledge node extraction
│       ├── tts.py             #   Text-to-speech
│       ├── sse.py             #   SSE event push
│       └── utils.py           #   Utility functions
├── routers/             # FastAPI route layer
│   ├── auth.py          #   Authentication (email verification code login)
│   ├── sessions.py      #   Learning sessions (SSE streaming)
│   ├── immersive.py     #   Immersive learning
│   ├── documents.py     #   Document management
│   ├── nodes.py         #   Knowledge graph nodes
│   ├── quiz.py          #   Quizzes
│   ├── cards.py         #   Knowledge cards
│   ├── brief.py         #   Daily brief
│   ├── settings.py      #   System settings
│   ├── users.py         #   User info
│   └── usage.py         #   Usage statistics
├── repositories/        # Data access layer
│   ├── base.py          #   BaseRepository (short-connection pattern)
│   ├── session_repo.py  #   Session data
│   ├── node_repo.py     #   Knowledge node data
│   ├── quiz_repo.py     #   Quiz data
│   ├── document_repo.py #   Document data
│   ├── user_repo.py     #   User data
│   ├── daily_plan_repo.py  # Study plan data
│   └── daily_brief_repo.py # Brief data
├── models/              # Pydantic data models
│   ├── session.py       #   Session model
│   ├── node.py          #   Knowledge node model
│   ├── quiz.py          #   Quiz model
│   ├── document.py      #   Document model
│   └── user.py          #   User model
├── database.py          # SQLite initialization & connection management
├── config.py            # Configuration management (environment variables)
├── dependencies.py      # FastAPI dependency injection
├── main.py              # Application entry point
└── requirements.txt     # Python dependencies
```

## Prerequisites

| Dependency | Version | Description | Required |
|------------|---------|-------------|:--------:|
| Python | ≥ 3.10 | Runtime | ✅ |
| XeLaTeX + latexmk | TeX Live 2023+ | Compile Beamer knowledge cards & slides | ✅ |
| SimplePlus Beamer Theme | master | Beamer slide theme | ✅ |
| macOS `say` + Tingting | macOS 13+ | TTS voice (auto-degrades on non-macOS) | Optional |

## Installation & Launch

```bash
# Install dependencies
pip install -r requirements.txt

# Install LaTeX (macOS)
brew install --cask mactex-no-gui

# Download Beamer theme
git clone https://github.com/pm25/SimplePlus-BeamerTheme.git SimplePlus-BeamerTheme

# Configure environment variables
cp .env.example .env
# Edit .env to fill in API keys and other settings

# Start service (default port 8080)
python main.py
```

## Environment Variables

| Variable | Description | Required | Example |
|----------|-------------|:--------:|---------|
| `OPENAI_API_KEY` | LLM API key | ✅ | `sk-xxx` |
| `OPENAI_BASE_URL` | LLM API endpoint | ✅ | `https://api.openai.com/v1` |
| `LLM_MODEL` | Model name | ✅ | `gpt-4o` |
| `BACKEND_HOST` | Listen address | No | `0.0.0.0` |
| `BACKEND_PORT` | Listen port | No | `8000` |
| `CORS_ORIGINS` | CORS allowed origins | No | `http://localhost:5173` |
| `TAVILY_API_KEY` | Web search API | No | `tvly-xxx` |
| `IMG_API_KEY` | Image generation API | No | `sk-xxx` |
| `IMG_BASE_URL` | Image generation endpoint | No | `https://api.openai.com/v1` |
| `IMG_MODEL` | Image generation model | No | `gpt-image-1` |
| `FREE_LLM_TOTAL` | Free LLM call quota | No | `100` |
| `FREE_SEARCH_TOTAL` | Free search quota | No | `30` |
| `FREE_IMAGE_TOTAL` | Free image generation quota | No | `15` |

## Database

Uses SQLite (WAL mode). Database files are auto-created in the `backend/data/` directory.

### Connection Management

Uses a **unified short-connection pattern**: all database operations acquire a short-lived connection via `with get_db() as conn`, which auto-commits and closes upon completion, preventing `database is locked` errors from long-held connections.

## API Overview

| Route Prefix | Description |
|-------------|-------------|
| `POST /api/auth/send-code` | Send email verification code |
| `POST /api/auth/verify-code` | Verification code login (auto-registers new users) |
| `GET/POST /api/sessions/...` | Learning session management |
| `POST /api/sessions/{id}/stream` | SSE streaming conversation |
| `POST /api/immersive/generate` | Immersive course generation |
| `GET/POST /api/documents/...` | Document management |
| `GET/POST /api/nodes/...` | Knowledge graph nodes |
| `GET/POST /api/quiz/...` | Quiz generation & grading |
| `GET /api/cards/...` | Knowledge cards |
| `GET /api/brief/...` | Daily brief |
| `GET/PUT /api/settings/...` | System settings |
| `GET /api/usage` | Usage statistics |

## Tech Stack

- **Web Framework**: FastAPI + uvicorn
- **Database**: SQLite (WAL mode)
- **Data Validation**: Pydantic v2
- **LLM**: OpenAI-compatible protocol
- **Content Generation**: XeLaTeX + Beamer
- **Search**: Tavily / arXiv / DuckDuckGo
- **Image**: OpenAI-compatible image API
- **Document Parsing**: pdfplumber / pdfminer
- **Streaming**: SSE (Server-Sent Events)
