"""Query routes for POST /queries endpoint."""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from backend.src.api.deps.auth import CurrentUser, require_repository_access
from backend.src.api.middleware.errors import ValidationError
from backend.src.api.schemas.query import QueryRequest, QueryResponse
from backend.src.config.constants import MAX_QUERY_LENGTH
from backend.src.config.logging import get_logger
from backend.src.services.agent_query_service import get_agent_query_service
from backend.src.services.query_service import get_query_service

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Access denied to specified repositories"},
        422: {"description": "Validation error"},
    },
)
async def create_query(
    request: QueryRequest,
    current_user: CurrentUser,
) -> QueryResponse:
    """Execute a query against indexed code repositories.

    Submit a natural language query to search across code and documentation.
    Returns an answer with citations to relevant file paths and line numbers.

    The query is scoped to repositories the authenticated user has access to.
    Branch overrides can be specified to query non-default branches.

    When agent_mode is enabled, the query uses a multi-step agentic workflow
    with tool use for more sophisticated reasoning.
    """
    logger.info(
        "Query request received",
        user_id=current_user.sub,
        query_length=len(request.query),
        agent_mode=request.agent_mode,
    )

    # Validate query length
    if len(request.query) > MAX_QUERY_LENGTH:
        raise ValidationError(
            message=f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters",
            field="query",
        )

    # Validate repository access
    if request.repositories:
        for repo_id in request.repositories:
            require_repository_access(repo_id, current_user)

    # Route to appropriate service based on agent_mode
    if request.agent_mode:
        service = get_agent_query_service()
    else:
        service = get_query_service()

    response = await service.process_query(
        request=request,
        user_id=current_user.sub,
        allowed_repositories=current_user.repository_ids or None,
        branch_overrides=current_user.branch_overrides or None,
    )

    logger.info(
        "Query processed successfully",
        user_id=current_user.sub,
        latency_ms=response.latency_ms,
        citation_count=len(response.citations),
        agent_mode=request.agent_mode,
    )

    return response
