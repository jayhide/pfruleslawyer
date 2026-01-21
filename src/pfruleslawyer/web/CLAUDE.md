# Web Module

FastAPI REST API for the Pathfinder Rules Lawyer.

## Files

- `app.py` - FastAPI application with routes
- `models.py` - Pydantic request/response models
- `streaming.py` - Async streaming logic for agentic loop

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
- `error` - An error occurred
- `done` - Response complete

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
