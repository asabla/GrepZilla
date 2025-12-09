"""Configuration-driven feature flags for branch overrides and size thresholds."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FeatureFlags(BaseSettings):
    """Feature flags for runtime behavior configuration."""

    model_config = SettingsConfigDict(
        env_prefix="FF_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Branch Override Features
    allow_branch_override: bool = Field(
        default=True,
        description="Allow users to specify non-default branches in queries",
    )
    track_all_branches: bool = Field(
        default=False,
        description="Track all branches (not just default) for indexing",
    )
    max_tracked_branches: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum branches to track per repository",
    )

    # Size Threshold Features
    enable_large_file_catalog: bool = Field(
        default=True,
        description="Catalog files over size limit (without indexing content)",
    )
    large_file_size_mb: int = Field(
        default=25,
        ge=1,
        le=100,
        description="File size threshold in MB for catalog-only handling",
    )
    enable_binary_detection: bool = Field(
        default=True,
        description="Detect and skip binary files automatically",
    )

    # Search Features
    enable_semantic_search: bool = Field(
        default=False,
        description="Enable vector/semantic search (requires embeddings)",
    )
    enable_reranking: bool = Field(
        default=False,
        description="Enable result reranking for improved relevance",
    )
    max_context_chunks: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum chunks to include in query context",
    )

    # Ingestion Features
    enable_incremental_ingestion: bool = Field(
        default=True,
        description="Only re-index changed files on update",
    )
    enable_scheduled_reindex: bool = Field(
        default=True,
        description="Enable periodic full reindex",
    )
    reindex_interval_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Hours between scheduled full reindex",
    )

    # Performance Features
    enable_query_caching: bool = Field(
        default=False,
        description="Cache query results for repeated queries",
    )
    query_cache_ttl_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Time-to-live for cached query results",
    )

    # Observability Features
    enable_detailed_metrics: bool = Field(
        default=True,
        description="Collect detailed performance metrics",
    )
    enable_trace_logging: bool = Field(
        default=False,
        description="Enable verbose trace-level logging",
    )

    @property
    def large_file_size_bytes(self) -> int:
        """Get large file size threshold in bytes.

        Returns:
            File size threshold in bytes.
        """
        return self.large_file_size_mb * 1024 * 1024


@lru_cache
def get_feature_flags() -> FeatureFlags:
    """Get cached feature flags instance.

    Returns:
        FeatureFlags instance loaded from environment.
    """
    return FeatureFlags()


def is_branch_override_allowed() -> bool:
    """Check if branch override is allowed.

    Returns:
        True if branch override feature is enabled.
    """
    return get_feature_flags().allow_branch_override


def get_file_size_limit() -> int:
    """Get file size limit for full indexing.

    Returns:
        File size limit in bytes.
    """
    return get_feature_flags().large_file_size_bytes


def is_semantic_search_enabled() -> bool:
    """Check if semantic search is enabled.

    Returns:
        True if semantic search feature is enabled.
    """
    return get_feature_flags().enable_semantic_search
