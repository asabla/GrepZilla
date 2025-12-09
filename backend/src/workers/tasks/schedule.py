"""Scheduled tasks for repository freshness."""

from datetime import datetime, timedelta, timezone
from typing import Any

from celery import shared_task
from celery.schedules import crontab

from backend.src.config.constants import SCHEDULED_REINDEX_HOURS
from backend.src.config.logging import get_logger
from backend.src.workers.tasks.ingestion import full_reindex_repository

logger = get_logger(__name__)


@shared_task(bind=True)
def check_stale_repositories(self) -> dict[str, Any]:
    """Check for repositories needing scheduled reindex.

    Runs periodically to identify repositories that haven't been
    indexed within the freshness window and enqueues reindex tasks.

    Returns:
        Summary of repositories checked and reindex tasks queued.
    """
    logger.info(
        "Checking for stale repositories",
        task_id=self.request.id,
    )

    result = {
        "repositories_checked": 0,
        "reindex_tasks_queued": 0,
        "errors": [],
    }

    try:
        # Calculate staleness threshold
        stale_threshold = datetime.now(timezone.utc) - timedelta(
            hours=SCHEDULED_REINDEX_HOURS
        )

        # TODO: Query database for stale repositories
        # stale_repos = await repository_service.find_stale_repositories(stale_threshold)

        # For now, placeholder
        stale_repos: list[dict[str, str]] = []

        for repo in stale_repos:
            try:
                # Queue full reindex
                full_reindex_repository.delay(
                    repository_id=repo["repository_id"],
                    branch_id=repo["branch_id"],
                )
                result["reindex_tasks_queued"] += 1

                logger.info(
                    "Queued reindex for stale repository",
                    repository_id=repo["repository_id"],
                    branch_id=repo["branch_id"],
                )

            except Exception as e:
                error_msg = f"Failed to queue reindex for {repo['repository_id']}: {e}"
                result["errors"].append(error_msg)
                logger.error(error_msg)

        result["repositories_checked"] = len(stale_repos)

        logger.info(
            "Stale repository check complete",
            repositories_checked=result["repositories_checked"],
            reindex_tasks_queued=result["reindex_tasks_queued"],
        )

    except Exception as e:
        logger.error(
            "Stale repository check failed",
            error=str(e),
        )
        result["errors"].append(str(e))
        raise

    return result


@shared_task(bind=True)
def cleanup_old_notifications(self, days_to_keep: int = 30) -> dict[str, Any]:
    """Clean up old processed notifications.

    Removes notification records older than the retention period
    to prevent unbounded table growth.

    Args:
        days_to_keep: Number of days to retain notifications.

    Returns:
        Cleanup summary.
    """
    logger.info(
        "Cleaning up old notifications",
        days_to_keep=days_to_keep,
        task_id=self.request.id,
    )

    result = {
        "notifications_deleted": 0,
        "errors": [],
    }

    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

        # TODO: Delete old notifications from database
        # deleted = await notification_service.delete_older_than(cutoff_date)

        deleted = 0  # Placeholder
        result["notifications_deleted"] = deleted

        logger.info(
            "Notification cleanup complete",
            notifications_deleted=result["notifications_deleted"],
            cutoff_date=cutoff_date.isoformat(),
        )

    except Exception as e:
        logger.error(
            "Notification cleanup failed",
            error=str(e),
        )
        result["errors"].append(str(e))
        raise

    return result


# Celery beat schedule configuration
# To be added to the Celery app configuration
CELERY_BEAT_SCHEDULE = {
    "check-stale-repositories": {
        "task": "backend.src.workers.tasks.schedule.check_stale_repositories",
        "schedule": crontab(hour="*/4"),  # Every 4 hours
    },
    "cleanup-old-notifications": {
        "task": "backend.src.workers.tasks.schedule.cleanup_old_notifications",
        "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM
    },
}
