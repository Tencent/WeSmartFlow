**English | [中文](./README.md)**

# WeSmartFlow Frontend

A Vue 3 single-page application providing a complete interactive interface for adaptive learning.

## Module Structure

```
frontend/
├── public/              # Static assets
│   ├── logo.jpg         #   App logo
│   ├── logo.png         #   Browser tab icon (rounded)
│   └── icons.svg        #   SVG icon set
├── src/
│   ├── views/           # Page views
│   │   ├── LoginView.vue       # Login (email / GitHub / WeChat)
│   │   ├── DashboardView.vue   # Today's Learning (study plan + heatmap)
│   │   ├── ChatView.vue        # AI Tutoring (interactive + immersive)
│   │   ├── GraphView.vue       # Knowledge graph visualization
│   │   ├── KnowledgeBase.vue   # Knowledge base management
│   │   ├── QuizView.vue        # Quiz center
│   │   ├── DocumentsView.vue   # Document management
│   │   ├── SessionsView.vue    # Learning history
│   │   ├── DailyBrief.vue      # Daily brief
│   │   ├── LearningPath.vue    # Learning path
│   │   ├── ProfileView.vue     # User profile
│   │   └── SettingsView.vue    # System settings
│   ├── components/      # Reusable components
│   │   ├── EduViz/      #   Interactive visualization sandbox
│   │   │   ├── EduVizSandbox.vue  # iframe sandbox renderer
│   │   │   ├── EduVizDemo.vue     # Visualization demo component
│   │   │   ├── eduviz-sdk.js      # EduViz SDK core library
│   │   │   └── sandboxTemplate.js # Sandbox HTML template
│   │   ├── HtmlCard/    #   HTML knowledge card renderer
│   │   │   └── HtmlCard.vue       # Safely renders Agent-generated HTML cards
│   │   ├── QuizCard/    #   Quiz card
│   │   │   └── QuizCard.vue       # Multi-type quiz interaction component
│   │   ├── VizCard/     #   Visualization card
│   │   │   └── VizCard.vue        # Visualization result display card
│   │   └── chat/        #   Chat helper components
│   │       ├── ThinkBlock.vue     # Agent thinking process display
│   │       └── ToolCallBlock.vue  # Tool call process display
│   ├── api/             # API client
│   │   ├── base.js      #   Base request wrapper (with token management)
│   │   ├── index.js     #   Unified exports
│   │   ├── auth.js      #   Auth API
│   │   ├── sessions.js  #   Session API (with SSE streaming)
│   │   ├── documents.js #   Document API
│   │   ├── nodes.js     #   Knowledge node API
│   │   ├── quizzes.js   #   Quiz API
│   │   ├── settings.js  #   Settings API
│   │   ├── brief.js     #   Brief API
│   │   └── user.js      #   User API
│   ├── composables/     # Vue composables
│   │   ├── useAuth.js   #   Auth state management
│   │   └── useTheme.js  #   Theme switching
│   ├── styles/          # Global styles
│   │   └── page-list.css#   List page common styles
│   ├── assets/          # Build-time processed assets
│   ├── App.vue          # Root component (sidebar layout)
│   ├── main.js          # App entry (router + global styles)
│   └── style.css        # Global CSS variables & base styles
├── index.html           # HTML entry
├── package.json         # Dependency config
├── vite.config.js       # Vite build config
├── eslint.config.js     # ESLint config
└── stylelint.config.cjs # Stylelint config
```

## Prerequisites

| Dependency | Version | Description     |
| ---------- | ------- | --------------- |
| Node.js    | ≥ 18    | Runtime         |
| npm        | ≥ 9     | Package manager |

## Installation & Launch

```bash
# Install dependencies
npm install

# Development mode (port 5173)
npm run dev

# Production build
npm run build

# Preview production build
npm run preview
```

## Core Dependencies

| Package    | Version | Purpose                      |
| ---------- | ------- | ---------------------------- |
| vue        | ^3.5    | UI framework                 |
| vue-router | ^4.6    | Route management             |
| marked     | ^18.0   | Markdown rendering           |
| katex      | ^0.16   | LaTeX math formula rendering |
| dompurify  | ^3.3    | HTML sanitization            |
| pdfjs-dist | ^5.6    | PDF file rendering           |
| pdf-lib    | ^1.17   | PDF file manipulation        |

## Pages

| Page             | Route        | Features                                                               |
| ---------------- | ------------ | ---------------------------------------------------------------------- |
| Login            | `/login`     | Multi-method login (email / GitHub / WeChat)                           |
| AI Tutoring      | `/chat`      | Interactive conversation learning + immersive course generation (home) |
| Today's Learning | `/dashboard` | Personalized study plan, learning heatmap, nodes due for review        |
| Knowledge Graph  | `/graph`     | Force-directed graph visualization, node details, mastery display      |
| Knowledge Base   | `/knowledge` | Knowledge node list management                                         |
| Quiz             | `/quiz`      | Multi-type quizzes (MCQ / fill-in-the-blank / true-false / open-ended) |
| Documents        | `/documents` | Document upload & knowledge extraction                                 |
| Learning History | `/sessions`  | Historical session list                                                |
| Daily Brief      | `/brief`     | AI-generated daily learning news                                       |
| Profile          | `/profile`   | User profile & learning statistics                                     |
| Settings         | `/settings`  | LLM configuration, system settings                                     |

## Features

- **SSE Streaming Conversations** — Real-time AI responses with Markdown + LaTeX + code highlighting
- **HTML Knowledge Cards** — Safely renders Agent-generated interactive HTML knowledge cards (DOMPurify sanitized)
- **EduViz Interactive Visualization** — iframe-sandboxed Agent-generated educational visualizations (algorithm demos, parameter exploration, etc.)
- **Quiz Cards** — Inline multi-type quizzes with instant feedback and grading
- **Immersive Learning** — Progressive multi-chapter slide presentation with audio playback
- **Knowledge Graph Visualization** — Force-directed graph + 3D mastery display
- **Agent Transparency** — Displays Agent thinking process and tool call details
- **Dark Theme** — Light / dark theme switching
- **Leave Confirmation** — Confirmation prompt when leaving during generation to prevent accidental interruption
- **Responsive Layout** — Optimized for desktop browsers

## Development Guidelines

- ESLint + Prettier code formatting
- Stylelint CSS linting
- Components use `<script setup>` Composition API
- CSS variables for unified theme color management
