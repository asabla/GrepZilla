"""Celery application configuration with Redis broker."""

from celery import Celery

from backend.src.config.settings import get_settings


def create_celery_app() -> Celery:
    """Create and configure the Celery application.

    Returns:
        Configured Celery application instance.
    """
    settings = get_settings()

    app = Celery(
        "grepzilla",
        broker=settings.redis_url,
        backend=settings.redis_result_backend,
    )

    # Configure Celery
    app.conf.update(
        # Task settings
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        # Task execution
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        # Result settings
        result_expires=3600,  # 1 hour
        # Worker settings
        worker_prefetch_multiplier=1,
        worker_concurrency=4,
        # Beat settings for scheduling
        beat_scheduler="celery.beat:PersistentScheduler",
        # Task autodiscovery
        imports=["backend.src.workers.tasks"],
    )

    # Configure periodic tasks (beat schedule)
    app.conf.beat_schedule = {
        "scheduled-reindex": {
            "task": "backend.src.workers.tasks.schedule.scheduled_reindex",
            "schedule": 3600.0,  # Every hour
        },
        "check-freshness": {
            "task": "backend.src.workers.tasks.schedule.check_freshness",
            "schedule": 300.0,  # Every 5 minutes
        },
    }

    return app


# Global Celery app instance
celery_app = create_celery_app()
