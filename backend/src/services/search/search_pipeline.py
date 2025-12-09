"""Search pipeline with branch-aware filters."""

from typing import Any

from backend.src.config.constants import DEFAULT_SEARCH_RESULTS, MAX_SEARCH_RESULTS
from backend.src.config.feature_flags import get_feature_flags
from backend.src.config.logging import get_logger
from backend.src.services.search.index_client import CHUNKS_INDEX, search

logger = get_logger(__name__)


class SearchResult:
    """Individual search result from Meilisearch."""

    def __init__(
        self,
        chunk_id: str,
        content: str,
        path: str,
        repository_id: str,
        branch_id: str,
        line_start: int,
        line_end: int,
        language: str | None,
        score: float,
    ) -> None:
        self.chunk_id = chunk_id
        self.content = content
        self.path = path
        self.repository_id = repository_id
        self.branch_id = branch_id
        self.line_start = line_start
        self.line_end = line_end
        self.language = language
        self.score = score

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "path": self.path,
            "repository_id": self.repository_id,
            "branch_id": self.branch_id,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "language": self.language,
            "score": self.score,
        }


class SearchPipeline:
    """Pipeline for searching indexed code with branch-aware filtering."""

    def __init__(
        self,
        repository_ids: list[str] | None = None,
        branch_overrides: dict[str, str] | None = None,
    ) -> None:
        """Initialize search pipeline.

        Args:
            repository_ids: Optional list of repository IDs to filter by.
            branch_overrides: Optional map of repo_id -> branch_id for filtering.
        """
        self.repository_ids = repository_ids or []
        self.branch_overrides = branch_overrides or {}
        self.flags = get_feature_flags()

    def _build_filter_expression(self) -> str | None:
        """Build Meilisearch filter expression from scope parameters.

        Returns:
            Filter expression string or None if no filters.
        """
        filters: list[str] = []

        # Filter by repository IDs if specified
        if self.repository_ids:
            repo_filter = " OR ".join(
                f'repository_id = "{repo_id}"' for repo_id in self.repository_ids
            )
            filters.append(f"({repo_filter})")

        # Add branch filters if specified
        if self.branch_overrides:
            branch_filters = []
            for repo_id, branch_id in self.branch_overrides.items():
                branch_filters.append(
                    f'(repository_id = "{repo_id}" AND branch_id = "{branch_id}")'
                )
            if branch_filters:
                filters.append(f"({' OR '.join(branch_filters)})")

        return " AND ".join(filters) if filters else None

    def search(
        self,
        query: str,
        limit: int = DEFAULT_SEARCH_RESULTS,
        offset: int = 0,
    ) -> list[SearchResult]:
        """Execute search query with filtering.

        Args:
            query: Search query string.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of SearchResult objects.
        """
        if limit > MAX_SEARCH_RESULTS:
            limit = MAX_SEARCH_RESULTS

        filter_expr = self._build_filter_expression()

        logger.debug(
            "Executing search",
            query=query[:100],
            filter=filter_expr,
            limit=limit,
        )

        try:
            results = search(
                index_name=CHUNKS_INDEX,
                query=query,
                filter_expression=filter_expr,
                limit=limit,
                offset=offset,
            )
        except Exception as e:
            logger.error("Search failed", error=str(e))
            return []

        # Convert raw results to SearchResult objects
        search_results: list[SearchResult] = []
        for hit in results.get("hits", []):
            search_results.append(
                SearchResult(
                    chunk_id=hit.get("id", ""),
                    content=hit.get("content", ""),
                    path=hit.get("path", ""),
                    repository_id=hit.get("repository_id", ""),
                    branch_id=hit.get("branch_id", ""),
                    line_start=hit.get("line_start", 1),
                    line_end=hit.get("line_end", 1),
                    language=hit.get("language"),
                    score=hit.get("_rankingScore", 0.0),
                )
            )

        logger.debug(
            "Search completed",
            result_count=len(search_results),
            processing_time_ms=results.get("processingTimeMs", 0),
        )

        return search_results

    def search_with_context(
        self,
        query: str,
        context_chunks: int | None = None,
    ) -> list[SearchResult]:
        """Search and retrieve context chunks for Q&A.

        Args:
            query: Search query string.
            context_chunks: Number of chunks to retrieve for context.

        Returns:
            List of SearchResult objects for context building.
        """
        if context_chunks is None:
            context_chunks = self.flags.max_context_chunks

        return self.search(query, limit=context_chunks)
