"""Request/response logging and timing instrumentation for queries."""

import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from backend.src.config.constants import QUERY_P95_LATENCY_MS
from backend.src.config.logging import get_logger, log_context

logger = get_logger(__name__)


class QueryMetrics:
    """Metrics collector for query operations."""

    def __init__(self) -> None:
        """Initialize query metrics collector."""
        self._query_count = 0
        self._total_latency_ms = 0
        self._latency_samples: list[int] = []
        self._error_count = 0
        self._slow_query_count = 0

    def record_query(
        self,
        latency_ms: int,
        success: bool = True,
        repository_count: int = 0,
        citation_count: int = 0,
    ) -> None:
        """Record a query execution.

        Args:
            latency_ms: Query processing time in milliseconds.
            success: Whether the query completed successfully.
            repository_count: Number of repositories queried.
            citation_count: Number of citations returned.
        """
        self._query_count += 1
        self._total_latency_ms += latency_ms
        self._latency_samples.append(latency_ms)

        # Keep only recent samples for p95 calculation
        if len(self._latency_samples) > 1000:
            self._latency_samples = self._latency_samples[-1000:]

        if not success:
            self._error_count += 1

        if latency_ms > QUERY_P95_LATENCY_MS:
            self._slow_query_count += 1
            logger.warning(
                "Slow query detected",
                latency_ms=latency_ms,
                threshold_ms=QUERY_P95_LATENCY_MS,
            )

        logger.debug(
            "Query metrics recorded",
            latency_ms=latency_ms,
            success=success,
            repository_count=repository_count,
            citation_count=citation_count,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get current query statistics.

        Returns:
            Dictionary with query statistics.
        """
        avg_latency = (
            self._total_latency_ms / self._query_count
            if self._query_count > 0
            else 0
        )

        p95_latency = self._calculate_percentile(95)

        return {
            "total_queries": self._query_count,
            "error_count": self._error_count,
            "slow_query_count": self._slow_query_count,
            "average_latency_ms": round(avg_latency, 2),
            "p95_latency_ms": p95_latency,
            "error_rate": (
                self._error_count / self._query_count
                if self._query_count > 0
                else 0
            ),
        }

    def _calculate_percentile(self, percentile: int) -> int:
        """Calculate latency percentile.

        Args:
            percentile: Percentile to calculate (0-100).

        Returns:
            Latency value at the specified percentile.
        """
        if not self._latency_samples:
            return 0

        sorted_samples = sorted(self._latency_samples)
        index = int(len(sorted_samples) * percentile / 100)
        return sorted_samples[min(index, len(sorted_samples) - 1)]


# Global metrics instance
_query_metrics: QueryMetrics | None = None


def get_query_metrics() -> QueryMetrics:
    """Get singleton query metrics instance.

    Returns:
        QueryMetrics instance.
    """
    global _query_metrics
    if _query_metrics is None:
        _query_metrics = QueryMetrics()
    return _query_metrics


@asynccontextmanager
async def track_query(
    query_id: str,
    user_id: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Context manager for tracking query execution.

    Args:
        query_id: Unique identifier for the query.
        user_id: Optional user ID for context.

    Yields:
        Dictionary to store query metadata during execution.
    """
    log_context(query_id=query_id, user_id=user_id)

    start_time = time.perf_counter()
    metadata: dict[str, Any] = {
        "success": True,
        "repository_count": 0,
        "citation_count": 0,
    }

    try:
        yield metadata
    except Exception as e:
        metadata["success"] = False
        metadata["error"] = str(e)
        raise
    finally:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        metadata["latency_ms"] = latency_ms

        get_query_metrics().record_query(
            latency_ms=latency_ms,
            success=metadata["success"],
            repository_count=metadata.get("repository_count", 0),
            citation_count=metadata.get("citation_count", 0),
        )

        logger.info(
            "Query execution tracked",
            query_id=query_id,
            latency_ms=latency_ms,
            success=metadata["success"],
        )
