"""Logging and tracing configuration shared by API and workers."""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from backend.src.config.settings import get_settings


def configure_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()

    # Determine log level based on environment
    log_level = logging.DEBUG if settings.debug else logging.INFO

    # Shared processors for all logging
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    # Development vs production rendering
    if settings.app_env == "development":
        # Human-readable output for development
        processors: list[Processor] = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # JSON output for production (easier to parse in log aggregators)
        processors = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.debug else logging.WARNING
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a logger instance.

    Args:
        name: Optional logger name for context.

    Returns:
        Configured structlog bound logger.
    """
    logger: structlog.BoundLogger = structlog.get_logger()
    if name:
        logger = logger.bind(logger_name=name)
    return logger


def log_context(**kwargs: Any) -> None:
    """Add context variables for structured logging.

    These variables will be included in all subsequent log entries
    within the current context (request/task).

    Args:
        **kwargs: Key-value pairs to add to logging context.
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_log_context() -> None:
    """Clear all context variables from structured logging."""
    structlog.contextvars.clear_contextvars()
