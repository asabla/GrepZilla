"""Query service combining chunk retrieval, rerank, and citation assembly."""

import time
from typing import Any

from backend.src.api.schemas.query import Citation, QueryRequest, QueryResponse
from backend.src.config.constants import MAX_CITATIONS
from backend.src.config.logging import get_logger
from backend.src.services.ai.llm import LLMClient, get_llm_client
from backend.src.services.search.prompt_builder import PromptBuilder
from backend.src.services.search.search_pipeline import SearchPipeline, SearchResult

logger = get_logger(__name__)


class QueryService:
    """Service for processing code search queries and generating answers."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        """Initialize query service.

        Args:
            llm_client: Optional LLM client. Uses singleton if not provided.
        """
        self.prompt_builder = PromptBuilder()
        self.llm_client = llm_client or get_llm_client()

    async def process_query(
        self,
        request: QueryRequest,
        user_id: str | None = None,
        allowed_repositories: list[str] | None = None,
        branch_overrides: dict[str, str] | None = None,
    ) -> QueryResponse:
        """Process a query and return an answer with citations.

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
            "Processing query",
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

        # Create search pipeline with filters
        pipeline = SearchPipeline(
            repository_ids=repository_ids,
            branch_overrides=effective_branches,
        )

        # Search for relevant chunks
        search_results = pipeline.search_with_context(request.query)

        # Build context and generate answer
        answer = self._generate_answer(request.query, search_results)

        # Assemble citations from search results
        citations = self._build_citations(search_results)

        # Calculate latency
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        logger.info(
            "Query processed",
            latency_ms=latency_ms,
            result_count=len(search_results),
            citation_count=len(citations),
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

    def _generate_answer(
        self,
        query: str,
        search_results: list[SearchResult],
    ) -> str:
        """Generate answer from search results.

        This is a sync wrapper that calls the async LLM method.
        For production use, consider making process_query fully async.

        Args:
            query: Original query text.
            search_results: Search results with code chunks.

        Returns:
            Generated answer text.
        """
        import asyncio

        return asyncio.get_event_loop().run_until_complete(
            self._generate_answer_async(query, search_results)
        )

    async def _generate_answer_async(
        self,
        query: str,
        search_results: list[SearchResult],
    ) -> str:
        """Generate answer from search results using LLM.

        Args:
            query: Original query text.
            search_results: Search results with code chunks.

        Returns:
            Generated answer text.
        """
        if not search_results:
            return (
                "I couldn't find any relevant code to answer your question. "
                "Please try rephrasing your query or expanding the repository scope."
            )

        # Build prompt using prompt builder
        prompt_data = self.prompt_builder.build_full_prompt(query, search_results)

        try:
            # Call LLM
            answer = await self.llm_client.complete(
                prompt=prompt_data["user"],
                system_prompt=prompt_data["system"],
            )

            logger.debug(
                "LLM answer generated",
                query_length=len(query),
                answer_length=len(answer),
            )

            return answer

        except Exception as e:
            logger.error(
                "Failed to generate LLM answer, falling back to simple response",
                error=str(e),
            )
            # Fallback to simple summary
            return self._generate_fallback_answer(query, search_results)

    def _generate_fallback_answer(
        self,
        query: str,
        search_results: list[SearchResult],
    ) -> str:
        """Generate a simple fallback answer when LLM is unavailable.

        Args:
            query: Original query text.
            search_results: Search results with code chunks.

        Returns:
            Simple answer text.
        """
        answer_parts = [
            f"Based on the codebase analysis, here's what I found about: {query}\n\n",
        ]

        # Summarize findings from search results
        paths_mentioned = set()
        for result in search_results[:5]:  # Top 5 results
            if result.path not in paths_mentioned:
                answer_parts.append(
                    f"- Found relevant code in `{result.path}` "
                    f"(lines {result.line_start}-{result.line_end})\n"
                )
                paths_mentioned.add(result.path)

        answer_parts.append(
            "\nPlease refer to the cited files for detailed implementation."
        )

        return "".join(answer_parts)

    def _build_citations(
        self,
        search_results: list[SearchResult],
    ) -> list[Citation]:
        """Build citations from search results.

        Args:
            search_results: Search results to convert to citations.

        Returns:
            List of Citation objects.
        """
        citations: list[Citation] = []
        seen_paths: set[tuple[str, str, str, int, int]] = set()

        for result in search_results[:MAX_CITATIONS]:
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
_query_service: QueryService | None = None


def get_query_service() -> QueryService:
    """Get singleton query service instance.

    Returns:
        QueryService instance.
    """
    global _query_service
    if _query_service is None:
        _query_service = QueryService()
    return _query_service
