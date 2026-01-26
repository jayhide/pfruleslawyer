# Frontend

React SPA frontend for the Pathfinder Rules Lawyer web application.

## Technology Stack

- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS v4
- **Markdown**: react-markdown with remark-gfm

## Project Structure

```
frontend/
├── src/
│   ├── components/           # React components
│   │   ├── Header.tsx        # App header with settings button
│   │   ├── SettingsPanel.tsx # Slide-out settings drawer
│   │   ├── ChatContainer.tsx # Message list container
│   │   ├── QueryInput.tsx    # Question input textarea
│   │   ├── UserMessage.tsx   # User message bubble
│   │   ├── AssistantMessage.tsx # AI response with markdown
│   │   └── index.ts          # Component exports
│   ├── hooks/
│   │   ├── useSettings.ts    # Settings with localStorage persistence
│   │   └── useStreamingQuestion.ts # SSE consumer and chat state
│   ├── services/
│   │   └── api.ts            # API calls and SSE streaming
│   ├── types/
│   │   └── index.ts          # TypeScript definitions
│   ├── App.tsx               # Main application component
│   ├── main.tsx              # React entry point
│   └── index.css             # Tailwind imports and base styles
├── index.html
├── vite.config.ts
├── package.json
└── tsconfig.json
```

## Development

All scripts can be run from the project root (via root `package.json`) or from `frontend/`:

```bash
# Install dependencies (from frontend/ directory)
npm install

# Start dev server (proxies /api to localhost:8000)
npm run dev

# Build for production (includes type check)
npm run build

# Type check only (no build)
npm run type-check

# Lint code
npm run lint

# Preview production build
npm run preview
```

### Available npm Scripts

| Script | Command | Description |
|--------|---------|-------------|
| `dev` | `vite` | Start development server with HMR |
| `build` | `tsc -b && vite build` | Type check then build for production |
| `type-check` | `tsc --noEmit` | Check TypeScript types without building |
| `lint` | `eslint .` | Run ESLint on all files |
| `preview` | `vite preview` | Preview the production build locally |

### Verifying Changes

After making frontend changes, run type checking and linting:

```bash
npm run type-check && npm run lint
```

The `npm run build` command also runs type checking first via `tsc -b`.

## Build Output

Production builds are output to `../data/static/` which FastAPI serves automatically.

## API Integration

The frontend connects to the FastAPI backend:

- **POST /api/ask** - Streaming SSE endpoint for questions
- **POST /api/ask/sync** - Synchronous JSON endpoint
- **GET /api/health** - Health check
- **GET /api/stats** - Vector store statistics

### SSE Event Types

The streaming endpoint sends these event types:

| Event | Data | Description |
|-------|------|-------------|
| `text` | `{ content: string }` | Text chunk from Claude |
| `tool_call` | `{ tool: string, query?: string, url?: string }` | Tool invocation |
| `tool_result` | `{ tool: string, ... }` | Tool result |
| `turn_complete` | `{ is_final: boolean }` | Agentic turn finished (reasoning vs final answer) |
| `error` | `{ message: string }` | Error occurred |
| `done` | `{ complete: boolean }` | Response complete |

## Settings

Settings are persisted to localStorage under the key `pf-rules-settings`:

- **model**: "sonnet" | "opus" (default: "sonnet")
- **n_results**: 1-20 (default: 7)
- **rerank**: boolean (default: true)
- **use_tools**: boolean (default: true)
- **reranker_model**: "ms-marco" | "bge-large" | "llm-haiku" | null (default: null)
- **verbose**: boolean (default: false) - Server-side debug logging
- **show_reasoning**: boolean (default: false) - Display AI reasoning in UI

## Component Details

### ChatContainer

Displays the message list with auto-scroll. Shows a welcome message when empty. During streaming, shows current turn text with pending styling when tool calls are in progress. Passes `showReasoning` setting to AssistantMessage components.

### QueryInput

Multi-line textarea with:
- Auto-resize up to 200px
- Enter to submit, Shift+Enter for newline
- Stop button during streaming

### SettingsPanel

Slide-out drawer with:
- Model selection (radio buttons)
- Result count slider
- Reranking toggle
- Follow-up searches toggle
- Reranker model dropdown
- Show reasoning toggle (Debug section)
- Verbose logging toggle (Debug section)
- Reset to defaults button

### AssistantMessage

Renders AI responses with:
- Markdown formatting via react-markdown
- Tool call badges showing searches and links
- Collapsible reasoning section (when show_reasoning enabled)
- Pending styling during multi-turn streaming
- Streaming cursor animation
