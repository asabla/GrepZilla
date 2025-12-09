"""Freshness and backlog metrics for observability."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.src.config.constants import (
    BACKLOG_CRITICAL_THRESHOLD,
    BACKLOG_WARNING_THRESHOLD,
    NOTIFICATION_TO_INDEX_MINUTES,
)
from backend.src.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FreshnessStatus:
    """Freshness status for a repository or branch."""

    status: str  # "fresh", "stale", "critical"
    last_indexed_at: datetime | None
    minutes_since_index: int | None
    freshness_window_minutes: int


@dataclass
class BacklogStatus:
    """Backlog status for pending notifications."""

    status: str  # "healthy", "warning", "critical"
    pending_count: int
    processing_count: int
    warning_threshold: int
    critical_threshold: int


@dataclass
class RepositoryMetrics:
    """Combined metrics for a repository."""

    repository_id: str
    repository_name: str
    freshness: FreshnessStatus
    backlog: BacklogStatus
    branches: list["BranchMetrics"]


@dataclass
class BranchMetrics:
    """Metrics for a single branch."""

    branch_id: str
    branch_name: str
    is_default: bool
    freshness: FreshnessStatus
    backlog: BacklogStatus


class FreshnessMetrics:
    """Service for computing freshness and backlog metrics."""

    def __init__(
        self,
        freshness_window_minutes: int = NOTIFICATION_TO_INDEX_MINUTES,
        backlog_warning: int = BACKLOG_WARNING_THRESHOLD,
        backlog_critical: int = BACKLOG_CRITICAL_THRESHOLD,
    ):
        """Initialize metrics service.

        Args:
            freshness_window_minutes: Minutes before considered stale.
            backlog_warning: Pending count for warning status.
            backlog_critical: Pending count for critical status.
        """
        self.freshness_window_minutes = freshness_window_minutes
        self.backlog_warning = backlog_warning
        self.backlog_critical = backlog_critical

    def compute_freshness_status(
        self,
        last_indexed_at: datetime | None,
    ) -> FreshnessStatus:
        """Compute freshness status based on last index time.

        Args:
            last_indexed_at: Timestamp of last successful index.

        Returns:
            FreshnessStatus with computed values.
        """
        if last_indexed_at is None:
            return FreshnessStatus(
                status="stale",
                last_indexed_at=None,
                minutes_since_index=None,
                freshness_window_minutes=self.freshness_window_minutes,
            )

        now = datetime.now(timezone.utc)
        delta = now - last_indexed_at
        minutes_since = int(delta.total_seconds() / 60)

        if minutes_since <= self.freshness_window_minutes:
            status = "fresh"
        elif minutes_since <= self.freshness_window_minutes * 2:
            status = "stale"
        else:
            status = "critical"

        return FreshnessStatus(
            status=status,
            last_indexed_at=last_indexed_at,
            minutes_since_index=minutes_since,
            freshness_window_minutes=self.freshness_window_minutes,
        )

    def compute_backlog_status(
        self,
        pending_count: int,
        processing_count: int = 0,
    ) -> BacklogStatus:
        """Compute backlog status based on pending notifications.

        Args:
            pending_count: Number of pending notifications.
            processing_count: Number of currently processing notifications.

        Returns:
            BacklogStatus with computed values.
        """
        total_backlog = pending_count + processing_count

        if total_backlog >= self.backlog_critical:
            status = "critical"
        elif total_backlog >= self.backlog_warning:
            status = "warning"
        else:
            status = "healthy"

        return BacklogStatus(
            status=status,
            pending_count=pending_count,
            processing_count=processing_count,
            warning_threshold=self.backlog_warning,
            critical_threshold=self.backlog_critical,
        )

    async def get_repository_metrics(
        self,
        repository_id: str,
    ) -> RepositoryMetrics | None:
        """Get full metrics for a repository.

        Args:
            repository_id: Repository UUID.

        Returns:
            RepositoryMetrics or None if not found.
        """
        # TODO: Query database for repository details
        # This would aggregate data from repositories, branches, and notifications
        logger.debug("Fetching repository metrics", repository_id=repository_id)
        return None

    async def get_all_metrics_summary(self) -> dict[str, Any]:
        """Get summary metrics across all repositories.

        Returns:
            Aggregated metrics summary.
        """
        logger.debug("Fetching all repository metrics")

        # TODO: Query database for aggregated metrics
        return {
            "total_repositories": 0,
            "repositories_fresh": 0,
            "repositories_stale": 0,
            "repositories_critical": 0,
            "total_pending_notifications": 0,
            "total_processing_notifications": 0,
            "backlog_status": "healthy",
        }

    def emit_metrics(
        self,
        repository_metrics: RepositoryMetrics,
    ) -> None:
        """Emit metrics to logging/monitoring system.

        Args:
            repository_metrics: Metrics to emit.
        """
        # Log structured metrics for monitoring systems to scrape
        logger.info(
            "repository_metrics",
            repository_id=repository_metrics.repository_id,
            repository_name=repository_metrics.repository_name,
            freshness_status=repository_metrics.freshness.status,
            backlog_status=repository_metrics.backlog.status,
            pending_count=repository_metrics.backlog.pending_count,
            processing_count=repository_metrics.backlog.processing_count,
        )

        # Emit alerts for critical status
        if repository_metrics.freshness.status == "critical":
            logger.warning(
                "repository_freshness_critical",
                repository_id=repository_metrics.repository_id,
                minutes_since_index=repository_metrics.freshness.minutes_since_index,
            )

        if repository_metrics.backlog.status == "critical":
            logger.warning(
                "repository_backlog_critical",
                repository_id=repository_metrics.repository_id,
                pending_count=repository_metrics.backlog.pending_count,
            )


# Service singleton
_freshness_metrics: FreshnessMetrics | None = None


def get_freshness_metrics() -> FreshnessMetrics:
    """Get freshness metrics service singleton."""
    global _freshness_metrics
    if _freshness_metrics is None:
        _freshness_metrics = FreshnessMetrics()
    return _freshness_metrics
