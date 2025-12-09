"""Performance and alert threshold configuration."""

from typing import Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.src.config.constants import (
    BACKLOG_CRITICAL_THRESHOLD,
    BACKLOG_WARNING_THRESHOLD,
    FRESHNESS_STALE_THRESHOLD_HOURS,
    NOTIFICATION_TO_INDEX_MINUTES,
    QUERY_P95_LATENCY_MS,
    SCHEDULED_REINDEX_HOURS,
)


class PerformanceConfig(BaseSettings):
    """Performance thresholds and alert configuration."""

    # Query latency targets (milliseconds)
    query_p50_latency_ms: int = Field(
        default=1000,
        description="Target p50 query latency in milliseconds",
    )
    query_p95_latency_ms: int = Field(
        default=QUERY_P95_LATENCY_MS,
        description="Target p95 query latency in milliseconds",
    )
    query_p99_latency_ms: int = Field(
        default=5000,
        description="Target p99 query latency in milliseconds",
    )

    # Freshness targets
    notification_to_index_minutes: int = Field(
        default=NOTIFICATION_TO_INDEX_MINUTES,
        description="Target time from notification to indexed (90th percentile)",
    )
    scheduled_reindex_hours: int = Field(
        default=SCHEDULED_REINDEX_HOURS,
        description="Interval for scheduled full re-indexing",
    )
    freshness_stale_threshold_hours: int = Field(
        default=FRESHNESS_STALE_THRESHOLD_HOURS,
        description="Hours after which a branch is considered stale",
    )

    # Backlog thresholds
    backlog_warning_threshold: int = Field(
        default=BACKLOG_WARNING_THRESHOLD,
        description="Backlog size to trigger warning alert",
    )
    backlog_critical_threshold: int = Field(
        default=BACKLOG_CRITICAL_THRESHOLD,
        description="Backlog size to trigger critical alert",
    )

    # Alert settings
    enable_slack_alerts: bool = Field(
        default=False,
        description="Enable Slack notifications for alerts",
    )
    slack_webhook_url: str | None = Field(
        default=None,
        description="Slack webhook URL for alerts",
    )

    enable_pagerduty_alerts: bool = Field(
        default=False,
        description="Enable PagerDuty for critical alerts",
    )
    pagerduty_routing_key: str | None = Field(
        default=None,
        description="PagerDuty routing key for incidents",
    )

    # Metrics export
    metrics_enabled: bool = Field(
        default=True,
        description="Enable Prometheus metrics export",
    )
    metrics_prefix: str = Field(
        default="grepzilla",
        description="Prefix for Prometheus metrics",
    )

    model_config = SettingsConfigDict(env_prefix="PERF_", case_sensitive=False)


# Singleton instance
_perf_config: PerformanceConfig | None = None


def get_perf_config() -> PerformanceConfig:
    """Get performance configuration singleton.

    Returns:
        PerformanceConfig instance.
    """
    global _perf_config
    if _perf_config is None:
        _perf_config = PerformanceConfig()
    return _perf_config


# Alert level constants
class AlertLevel:
    """Alert severity levels."""

    INFO: Final[str] = "info"
    WARNING: Final[str] = "warning"
    CRITICAL: Final[str] = "critical"


def check_latency_threshold(
    latency_ms: int,
    config: PerformanceConfig | None = None,
) -> str:
    """Check query latency against thresholds.

    Args:
        latency_ms: Observed latency in milliseconds.
        config: Optional config override.

    Returns:
        Alert level string.
    """
    if config is None:
        config = get_perf_config()

    if latency_ms > config.query_p99_latency_ms:
        return AlertLevel.CRITICAL
    if latency_ms > config.query_p95_latency_ms:
        return AlertLevel.WARNING
    return AlertLevel.INFO


def check_backlog_threshold(
    backlog_size: int,
    config: PerformanceConfig | None = None,
) -> str:
    """Check backlog size against thresholds.

    Args:
        backlog_size: Current backlog size.
        config: Optional config override.

    Returns:
        Alert level string.
    """
    if config is None:
        config = get_perf_config()

    if backlog_size >= config.backlog_critical_threshold:
        return AlertLevel.CRITICAL
    if backlog_size >= config.backlog_warning_threshold:
        return AlertLevel.WARNING
    return AlertLevel.INFO


def check_freshness_threshold(
    hours_since_index: float,
    config: PerformanceConfig | None = None,
) -> str:
    """Check freshness against thresholds.

    Args:
        hours_since_index: Hours since last successful index.
        config: Optional config override.

    Returns:
        Alert level string.
    """
    if config is None:
        config = get_perf_config()

    # Critical if more than 2x the stale threshold
    if hours_since_index > config.freshness_stale_threshold_hours * 2:
        return AlertLevel.CRITICAL
    if hours_since_index > config.freshness_stale_threshold_hours:
        return AlertLevel.WARNING
    return AlertLevel.INFO
