"""Configuration package for GrepZilla backend.

This package contains all configuration modules:

- settings: Application settings from environment variables
- constants: File limits, performance budgets, and other constants
- logging: Structured logging configuration
- feature_flags: Feature flag configuration
- perf: Performance thresholds and alerting configuration
"""

from backend.src.config.constants import (
    BACKLOG_CRITICAL_THRESHOLD,
    BACKLOG_WARNING_THRESHOLD,
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SIZE_TOKENS,
    FRESHNESS_STALE_THRESHOLD_HOURS,
    MAX_BATCH_SIZE,
    MAX_CITATIONS,
    MAX_CHUNKS_PER_FILE,
    MAX_FILE_SIZE_BYTES,
    MAX_QUERY_LENGTH,
    MAX_REPOS_PER_QUERY,
    MAX_SEARCH_RESULTS,
    NOTIFICATION_TO_INDEX_MINUTES,
    QUERY_P95_LATENCY_MS,
    SCHEDULED_REINDEX_HOURS,
)
from backend.src.config.feature_flags import FeatureFlags, get_feature_flags
from backend.src.config.logging import configure_logging, get_logger
from backend.src.config.perf import (
    AlertLevel,
    PerformanceConfig,
    check_backlog_threshold,
    check_freshness_threshold,
    check_latency_threshold,
    get_perf_config,
)
from backend.src.config.settings import Settings, get_settings

__all__ = [
    # Settings
    "Settings",
    "get_settings",
    # Logging
    "get_logger",
    "configure_logging",
    # Feature flags
    "FeatureFlags",
    "get_feature_flags",
    # Performance
    "PerformanceConfig",
    "AlertLevel",
    "get_perf_config",
    "check_latency_threshold",
    "check_backlog_threshold",
    "check_freshness_threshold",
    # Constants
    "MAX_FILE_SIZE_BYTES",
    "MAX_BATCH_SIZE",
    "CHUNK_SIZE_TOKENS",
    "CHUNK_OVERLAP_TOKENS",
    "MAX_CHUNKS_PER_FILE",
    "QUERY_P95_LATENCY_MS",
    "NOTIFICATION_TO_INDEX_MINUTES",
    "SCHEDULED_REINDEX_HOURS",
    "FRESHNESS_STALE_THRESHOLD_HOURS",
    "BACKLOG_WARNING_THRESHOLD",
    "BACKLOG_CRITICAL_THRESHOLD",
    "MAX_QUERY_LENGTH",
    "MAX_REPOS_PER_QUERY",
    "MAX_SEARCH_RESULTS",
    "MAX_CITATIONS",
]
