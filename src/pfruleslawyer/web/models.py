"""Pydantic models for the web API."""

from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Request body for asking a rules question."""

    question: str = Field(..., min_length=1, description="The rules question to ask")
    n_results: int = Field(
        default=7, ge=1, le=20, description="Number of sections to retrieve"
    )
    model: Literal["sonnet", "opus"] = Field(
        default="sonnet", description="Claude model to use"
    )
    rerank: bool = Field(
        default=True, description="Whether to use cross-encoder reranking"
    )
    use_tools: bool = Field(
        default=True, description="Whether to allow follow-up searches"
    )
    reranker_model: Literal["ms-marco", "bge-large"] | None = Field(
        default=None, description="Reranker model (default: ms-marco)"
    )


class AskResponse(BaseModel):
    """Non-streaming response for a rules question."""

    answer: str
    question: str


class HealthResponse(BaseModel):
    """Response for health check endpoint."""

    status: str = "ok"
    version: str = "0.1.0"


class StatsResponse(BaseModel):
    """Response for stats endpoint."""

    total_sections: int
    index_loaded: bool
