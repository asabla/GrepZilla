"""Query request/response schemas with citations."""

from pydantic import BaseModel, ConfigDict, Field

from backend.src.config.constants import MAX_QUERY_LENGTH, MAX_REPOS_PER_QUERY


class Citation(BaseModel):
    """Citation to a specific code location."""

    repository: str = Field(..., description="Repository name or ID")
    branch: str = Field(..., description="Branch name")
    path: str = Field(..., description="File path within repository")
    line_start: int = Field(..., ge=1, description="Starting line number (1-indexed)")
    line_end: int = Field(..., ge=1, description="Ending line number (1-indexed)")
    snippet: str | None = Field(
        default=None,
        description="Optional code snippet from the cited location",
    )


class QueryRequest(BaseModel):
    """Request schema for POST /queries."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=MAX_QUERY_LENGTH,
        description="Natural language query about the codebase",
    )
    repositories: list[str] | None = Field(
        default=None,
        max_length=MAX_REPOS_PER_QUERY,
        description="Optional list of repository IDs to scope the query",
    )
    branches: dict[str, str] | None = Field(
        default=None,
        description="Optional map of repo_id -> branch name overrides",
    )
    agent_mode: bool = Field(
        default=False,
        description="Enable agent mode for multi-step reasoning with tool use",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "How does the authentication middleware work?",
                "repositories": ["repo-123", "repo-456"],
                "branches": {"repo-123": "feature-branch"},
                "agent_mode": False,
            }
        }
    )


class QueryResponse(BaseModel):
    """Response schema for POST /queries."""

    answer: str = Field(..., description="Generated answer to the query")
    citations: list[Citation] = Field(
        default_factory=list,
        description="List of citations to relevant code locations",
    )
    latency_ms: int = Field(
        ..., ge=0, description="Query processing time in milliseconds"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "The authentication middleware validates JWT tokens...",
                "citations": [
                    {
                        "repository": "backend",
                        "branch": "main",
                        "path": "src/middleware/auth.py",
                        "line_start": 45,
                        "line_end": 78,
                        "snippet": "def validate_token(token: str) -> bool:",
                    }
                ],
                "latency_ms": 1250,
            }
        }
    )


class QueryErrorResponse(BaseModel):
    """Error response schema for query endpoints."""

    error: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code")
    details: dict | None = Field(default=None, description="Additional error details")
