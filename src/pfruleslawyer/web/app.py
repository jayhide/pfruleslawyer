"""FastAPI application for the Pathfinder Rules Lawyer API."""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from pfruleslawyer.rag import ask_rules_question
from pfruleslawyer.search import RulesVectorStore
from pfruleslawyer.web.models import (
    AskRequest,
    AskResponse,
    HealthResponse,
    StatsResponse,
)
from pfruleslawyer.web.streaming import stream_rules_question

# Static files directory (built frontend)
STATIC_DIR = Path(__file__).parent.parent.parent.parent / "data" / "static"

# Global store reference for stats endpoint
_store: RulesVectorStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown."""
    global _store
    # Initialize vector store on startup
    _store = RulesVectorStore()
    yield
    # Cleanup on shutdown
    _store = None


app = FastAPI(
    title="Pathfinder Rules Lawyer API",
    description="RAG-powered Pathfinder 1e rules assistant",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@app.get("/api/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    """Get vector store statistics."""
    if _store is None:
        return StatsResponse(total_sections=0, index_loaded=False)

    count = _store.collection.count()
    return StatsResponse(total_sections=count, index_loaded=True)


@app.post("/api/ask")
async def ask_streaming(request: AskRequest):
    """Ask a rules question with streaming response (SSE)."""

    async def event_generator():
        try:
            async for event in stream_rules_question(
                question=request.question,
                n_results=request.n_results,
                model=request.model,
                rerank=request.rerank,
                use_tools=request.use_tools,
                reranker_model=request.reranker_model,
                verbose=request.verbose,
            ):
                yield {"event": event["event"], "data": json.dumps(event["data"])}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_generator())


@app.post("/api/ask/sync", response_model=AskResponse)
async def ask_sync(request: AskRequest) -> AskResponse:
    """Ask a rules question with non-streaming JSON response.

    This endpoint uses the existing synchronous ask_rules_question function,
    which is simpler but doesn't provide streaming updates.
    """
    import asyncio

    loop = asyncio.get_event_loop()
    answer = await loop.run_in_executor(
        None,
        lambda: ask_rules_question(
            question=request.question,
            n_results=request.n_results,
            model=request.model,
            verbose=False,
            rerank=request.rerank,
            use_tools=request.use_tools,
            reranker_model=request.reranker_model,
        ),
    )

    return AskResponse(answer=answer, question=request.question)


# Static file serving for frontend
if STATIC_DIR.exists():
    # Mount static assets (JS, CSS, etc.)
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA for all non-API routes."""
        # Don't serve SPA for API routes (should never reach here, but just in case)
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        # Check if it's a static file that exists
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)

        # Otherwise serve index.html for SPA routing
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)

        raise HTTPException(status_code=404, detail="Frontend not built")
