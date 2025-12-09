"""Agent-based query service using OpenAI Agents SDK."""

import time

from backend.src.api.schemas.query import Citation, QueryRequest, QueryResponse
from backend.src.config.constants import MAX_CITATIONS
from backend.src.config.logging import get_logger
from backend.src.services.ai.agent import AgentClient, get_agent_client

logger = get_logger(__name__)


class AgentQueryService:
    """Service for processing queries using agentic workflow."""

    def __init__(self, agent_client: AgentClient | None = None) -> None:
        """Initialize agent query service.

        Args:
            agent_client: Optional agent client. Uses singleton if not provided.
        """
        self.agent_client = agent_client or get_agent_client()

    async def process_query(
        self,
        request: QueryRequest,
        user_id: str | None = None,
        allowed_repositories: list[str] | None = None,
        branch_overrides: dict[str, str] | None = None,
    ) -> QueryResponse:
        """Process a query using agentic workflow.

        The agent will use tools to search the codebase and reason through
        the query step by step before providing a final answer.

        Args:
            request: Query request from user.
            user_id: Optional user ID for logging/tracking.
            allowed_repositories: Optional list of repos user can access.
            branch_overrides: Optional branch overrides from auth claims.

        Returns:
            QueryResponse with answer and citations.
        """
        start_time = time.perf_counter()

        logger.info(
            "Processing agent query",
            query=request.query[:100],
            user_id=user_id,
            repository_count=len(request.repositories or []),
        )

        # Determine repository scope
        repository_ids = self._resolve_repository_scope(
            request.repositories,
            allowed_repositories,
        )

        # Merge branch overrides (request overrides take precedence)
        effective_branches = {**(branch_overrides or {}), **(request.branches or {})}

        # Run the agent
        try:
            result = await self.agent_client.run_agent(
                query=request.query,
                repository_ids=repository_ids,
                branch_overrides=effective_branches,
            )

            # Extract answer from agent result
            answer = result.final_output or "The agent could not generate an answer."

            # Extract citations from tool call results
            search_results = self.agent_client.extract_citations_from_result(result)
            citations = self._build_citations(search_results)

        except Exception as e:
            logger.error(
                "Agent query failed",
                error=str(e),
                user_id=user_id,
            )
            answer = (
                "An error occurred while processing your query with the agent. "
                "Please try again or use standard query mode."
            )
            citations = []

        # Calculate latency
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        logger.info(
            "Agent query processed",
            latency_ms=latency_ms,
            citation_count=len(citations),
            user_id=user_id,
        )

        return QueryResponse(
            answer=answer,
            citations=citations,
            latency_ms=latency_ms,
        )

    def _resolve_repository_scope(
        self,
        requested_repos: list[str] | None,
        allowed_repos: list[str] | None,
    ) -> list[str]:
        """Resolve final repository scope for query.

        Args:
            requested_repos: Repositories requested by user.
            allowed_repos: Repositories user is allowed to access.

        Returns:
            List of repository IDs to search.
        """
        if not requested_repos:
            # Use all allowed repositories if none specified
            return allowed_repos or []

        if not allowed_repos:
            # No access control, use requested repos
            return requested_repos

        # Intersection of requested and allowed
        return [r for r in requested_repos if r in allowed_repos]

    def _build_citations(
        self,
        search_results: list,
    ) -> list[Citation]:
        """Build citations from search results.

        Args:
            search_results: Search results to convert to citations.

        Returns:
            List of Citation objects.
        """
        from backend.src.services.search.search_pipeline import SearchResult

        citations: list[Citation] = []
        seen_paths: set[tuple[str, str, str, int, int]] = set()

        for result in search_results[:MAX_CITATIONS]:
            if not isinstance(result, SearchResult):
                continue

            # Deduplicate by path and line range
            key = (
                result.repository_id,
                result.branch_id,
                result.path,
                result.line_start,
                result.line_end,
            )
            if key in seen_paths:
                continue
            seen_paths.add(key)

            citations.append(
                Citation(
                    repository=result.repository_id,
                    branch=result.branch_id,
                    path=result.path,
                    line_start=result.line_start,
                    line_end=result.line_end,
                    snippet=result.content[:200] if result.content else None,
                )
            )

        return citations


# Singleton instance
_agent_query_service: AgentQueryService | None = None


def get_agent_query_service() -> AgentQueryService:
    """Get singleton agent query service instance.

    Returns:
        AgentQueryService instance.
    """
    global _agent_query_service
    if _agent_query_service is None:
        _agent_query_service = AgentQueryService()
    return _agent_query_service


def reset_agent_query_service() -> None:
    """Reset the agent query service singleton (for testing)."""
    global _agent_query_service
    _agent_query_service = None
