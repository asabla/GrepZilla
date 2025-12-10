"""Meilisearch client setup and index bootstrap."""

from functools import lru_cache
from typing import Any

import meilisearch
from meilisearch.index import Index

from backend.src.config.logging import get_logger
from backend.src.config.settings import get_settings

logger = get_logger(__name__)

# Index names
CHUNKS_INDEX = "chunks"
ARTIFACTS_INDEX = "artifacts"


def get_client() -> meilisearch.Client:
    """Get Meilisearch client instance.

    Returns:
        Configured Meilisearch client.
    """
    settings = get_settings()

    api_key = None
    if settings.meilisearch_api_key:
        api_key = settings.meilisearch_api_key.get_secret_value()

    return meilisearch.Client(settings.meilisearch_url, api_key)


@lru_cache
def get_index_name(base_name: str) -> str:
    """Get full index name with prefix.

    Args:
        base_name: Base name of the index.

    Returns:
        Full index name with configured prefix.
    """
    settings = get_settings()
    return f"{settings.meilisearch_index_prefix}_{base_name}"


def get_chunks_index() -> Index:
    """Get the chunks index for text search.

    Returns:
        Meilisearch Index instance for chunks.
    """
    client = get_client()
    return client.index(get_index_name(CHUNKS_INDEX))


def get_artifacts_index() -> Index:
    """Get the artifacts index for file metadata.

    Returns:
        Meilisearch Index instance for artifacts.
    """
    client = get_client()
    return client.index(get_index_name(ARTIFACTS_INDEX))


def bootstrap_indexes() -> None:
    """Create and configure Meilisearch indexes.

    This should be called during application startup or as a setup task.
    """
    client = get_client()
    logger.info("Bootstrapping Meilisearch indexes")

    # Create chunks index with settings
    chunks_index_name = get_index_name(CHUNKS_INDEX)
    try:
        client.create_index(chunks_index_name, {"primaryKey": "id"})
        logger.info("Created chunks index", index=chunks_index_name)
    except meilisearch.errors.MeilisearchApiError as e:
        if "index_already_exists" not in str(e):
            raise
        logger.debug("Chunks index already exists", index=chunks_index_name)

    # Configure chunks index
    chunks_index = client.index(chunks_index_name)
    chunks_index.update_settings(
        {
            "searchableAttributes": [
                "content",
                "path",
                "language",
            ],
            "filterableAttributes": [
                "repository_id",
                "branch_id",
                "artifact_id",
                "language",
                "file_type",
                "chunking_mode",
            ],
            "sortableAttributes": [
                "created_at",
                "line_start",
                "start_index",
            ],
            "displayedAttributes": [
                "id",
                "content",
                "path",
                "repository_id",
                "branch_id",
                "artifact_id",
                "line_start",
                "line_end",
                "start_index",
                "end_index",
                "language",
                "file_type",
                "chunking_mode",
            ],
        }
    )

    # Create artifacts index with settings
    artifacts_index_name = get_index_name(ARTIFACTS_INDEX)
    try:
        client.create_index(artifacts_index_name, {"primaryKey": "id"})
        logger.info("Created artifacts index", index=artifacts_index_name)
    except meilisearch.errors.MeilisearchApiError as e:
        if "index_already_exists" not in str(e):
            raise
        logger.debug("Artifacts index already exists", index=artifacts_index_name)

    # Configure artifacts index
    artifacts_index = client.index(artifacts_index_name)
    artifacts_index.update_settings(
        {
            "searchableAttributes": [
                "path",
            ],
            "filterableAttributes": [
                "repository_id",
                "branch_id",
                "file_type",
                "parse_status",
            ],
            "sortableAttributes": [
                "path",
                "size_bytes",
                "last_indexed_at",
            ],
        }
    )

    logger.info("Meilisearch indexes bootstrapped successfully")


def add_documents(index_name: str, documents: list[dict[str, Any]]) -> str:
    """Add documents to a Meilisearch index.

    Args:
        index_name: Name of the index (without prefix).
        documents: List of documents to add.

    Returns:
        Task UID for tracking the async operation.
    """
    client = get_client()
    index = client.index(get_index_name(index_name))
    task = index.add_documents(documents)
    return str(task.task_uid)


def delete_documents(
    index_name: str,
    filter_expression: str,
) -> str:
    """Delete documents from a Meilisearch index by filter.

    Args:
        index_name: Name of the index (without prefix).
        filter_expression: Meilisearch filter expression.

    Returns:
        Task UID for tracking the async operation.
    """
    client = get_client()
    index = client.index(get_index_name(index_name))
    task = index.delete_documents({"filter": filter_expression})
    return str(task.task_uid)


def search(
    index_name: str,
    query: str,
    filter_expression: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Search documents in a Meilisearch index.

    Args:
        index_name: Name of the index (without prefix).
        query: Search query string.
        filter_expression: Optional Meilisearch filter expression.
        limit: Maximum number of results.
        offset: Number of results to skip.

    Returns:
        Search results from Meilisearch.
    """
    client = get_client()
    index = client.index(get_index_name(index_name))

    search_params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
    }

    if filter_expression:
        search_params["filter"] = filter_expression

    return index.search(query, search_params)


class MeilisearchClient:
    """Async-compatible Meilisearch client wrapper."""

    def __init__(self) -> None:
        """Initialize Meilisearch client."""
        self._client = get_client()

    async def add_documents(
        self,
        index_name: str,
        documents: list[dict[str, Any]],
    ) -> str:
        """Add documents to an index.

        Args:
            index_name: Name of the index (without prefix).
            documents: List of documents to add.

        Returns:
            Task UID for tracking.
        """
        full_index_name = get_index_name(index_name)
        index = self._client.index(full_index_name)
        task = index.add_documents(documents)
        return str(task.task_uid)

    async def delete_documents_by_filter(
        self,
        index_name: str,
        filter_expression: str,
    ) -> int:
        """Delete documents by filter.

        Args:
            index_name: Name of the index (without prefix).
            filter_expression: Meilisearch filter expression.

        Returns:
            Approximate number of documents deleted.
        """
        full_index_name = get_index_name(index_name)
        index = self._client.index(full_index_name)

        # Get count before deletion for estimate
        try:
            stats = index.get_stats()
            count_before = stats.number_of_documents
        except Exception:
            count_before = 0

        task = index.delete_documents({"filter": filter_expression})

        # Wait for task completion
        self._client.wait_for_task(task.task_uid, timeout_in_ms=30000)

        # Get count after
        try:
            stats = index.get_stats()
            count_after = stats.number_of_documents
            return max(0, count_before - count_after)
        except Exception:
            return 0

    async def search(
        self,
        index_name: str,
        query: str,
        filter_expression: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search documents in an index.

        Args:
            index_name: Name of the index (without prefix).
            query: Search query string.
            filter_expression: Optional Meilisearch filter expression.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            Search results from Meilisearch.
        """
        return search(index_name, query, filter_expression, limit, offset)

    # =========================================================================
    # Synchronous methods for Celery workers
    # =========================================================================

    def add_documents_sync(
        self,
        index_name: str,
        documents: list[dict[str, Any]],
    ) -> str:
        """Add documents to an index (synchronous version).

        Args:
            index_name: Name of the index (without prefix).
            documents: List of documents to add.

        Returns:
            Task UID for tracking.
        """
        full_index_name = get_index_name(index_name)
        index = self._client.index(full_index_name)
        task = index.add_documents(documents)
        return str(task.task_uid)

    def delete_documents_by_filter_sync(
        self,
        index_name: str,
        filter_expression: str,
    ) -> int:
        """Delete documents by filter (synchronous version).

        Args:
            index_name: Name of the index (without prefix).
            filter_expression: Meilisearch filter expression.

        Returns:
            Approximate number of documents deleted.
        """
        full_index_name = get_index_name(index_name)
        index = self._client.index(full_index_name)

        # Get count before deletion for estimate
        try:
            stats = index.get_stats()
            count_before = stats.number_of_documents
        except Exception:
            count_before = 0

        task = index.delete_documents({"filter": filter_expression})

        # Wait for task completion
        self._client.wait_for_task(task.task_uid, timeout_in_ms=30000)

        # Get count after
        try:
            stats = index.get_stats()
            count_after = stats.number_of_documents
            return max(0, count_before - count_after)
        except Exception:
            return 0


# Client singleton
_meilisearch_client: MeilisearchClient | None = None


def get_meilisearch_client() -> MeilisearchClient:
    """Get Meilisearch client singleton.

    Returns:
        MeilisearchClient instance.
    """
    global _meilisearch_client
    if _meilisearch_client is None:
        _meilisearch_client = MeilisearchClient()
    return _meilisearch_client
