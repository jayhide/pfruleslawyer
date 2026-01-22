# Web Module

FastAPI REST API for the Pathfinder Rules Lawyer with integrated frontend serving.

## Files

- `app.py` - FastAPI application with routes and static file serving
- `models.py` - Pydantic request/response models
- `streaming.py` - Async streaming logic for agentic loop

## Frontend

The app serves the React frontend from `data/static/` when the build exists. Build the frontend with:

```bash
cd frontend && npm run build
```

Then access the web UI at `http://localhost:8000/`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ask` | Ask question (SSE streaming) |
| POST | `/api/ask/sync` | Ask question (JSON response) |
| GET | `/api/health` | Health check |
| GET | `/api/stats` | Vector store statistics |

## Streaming

The `/api/ask` endpoint uses Server-Sent Events (SSE) to stream responses as they're generated. Events:

- `text` - Text chunk from Claude
- `tool_call` - Claude is calling a tool (search_rules or follow_link)
- `tool_result` - Tool execution completed
- `turn_complete` - Agentic turn finished, with `is_final` flag indicating if this was the final answer or intermediate reasoning
- `error` - An error occurred
- `done` - Response complete

### Turn Complete Event

The `turn_complete` event helps the frontend distinguish between reasoning (text before tool calls) and the final answer. Each agentic turn emits this event:

- `is_final: false` - The text just streamed was reasoning; more tool calls will follow
- `is_final: true` - The text just streamed was the final answer

This enables the frontend to accumulate reasoning separately and display only the final answer by default.

## Usage

Start the server:
```bash
poetry run pfrules-server
poetry run pfrules-server --port 8080
poetry run pfrules-server --reload  # development mode
```

Example requests:
```bash
# Streaming
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How does grappling work?"}' \
  --no-buffer

# Non-streaming
curl -X POST http://localhost:8000/api/ask/sync \
  -H "Content-Type: application/json" \
  -d '{"question": "How does grappling work?"}'
```

## Request Parameters

- `question` (required) - The rules question to ask
- `n_results` (default: 7) - Number of sections to retrieve
- `model` (default: "sonnet") - Claude model: "sonnet" or "opus"
- `rerank` (default: true) - Use cross-encoder reranking
- `use_tools` (default: true) - Allow follow-up searches
- `reranker_model` (default: null) - Reranker: "ms-marco" or "bge-large"
- `verbose` (default: false) - Print debug output to server terminal

## Verbose Logging

When `verbose=true`, the server prints detailed debug information to stderr:

- **Initial search**: Query, retrieved sections with titles, sources, and score breakdowns
- **Context**: Full prompt sent to the model (in verbose mode)
- **Tool calls**: Search queries and follow_link URLs
- **Tool results**: Retrieved sections with content (in verbose mode)
- **Reasoning**: Model's reasoning text before tool calls

This mirrors the CLI's `-v` flag output. Enable via the Settings panel in the frontend or by adding `"verbose": true` to API requests.
