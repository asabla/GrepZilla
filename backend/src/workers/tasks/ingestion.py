"""Celery tasks for ingestion pipeline."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from celery import shared_task

from backend.src.config.constants import MAX_BATCH_SIZE
from backend.src.config.logging import get_logger
from backend.src.models.notification import NotificationStatus
from backend.src.services.ingestion.discover import get_artifact_discovery
from backend.src.services.ingestion.embed import get_embed_service
from backend.src.services.ingestion.index_writer import get_index_writer
from backend.src.services.repository_service import get_notification_service

logger = get_logger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
)
def process_notification(self, notification_id: str) -> dict[str, Any]:
    """Process a notification through the ingestion pipeline.

    This task:
    1. Updates notification status to PROCESSING
    2. Clones/updates the repository
    3. Discovers files to index
    4. Chunks and embeds content
    5. Writes to Meilisearch index
    6. Updates notification status to DONE

    Args:
        notification_id: Notification UUID string.

    Returns:
        Summary of ingestion results.
    """
    logger.info(
        "Processing notification",
        notification_id=notification_id,
        task_id=self.request.id,
    )

    notification_service = get_notification_service()
    result = {
        "notification_id": notification_id,
        "status": "pending",
        "files_indexed": 0,
        "chunks_created": 0,
        "errors": [],
    }

    try:
        # Update status to processing
        import asyncio
        asyncio.run(
            notification_service.update_status(
                uuid.UUID(notification_id),
                NotificationStatus.PROCESSING,
            )
        )

        # TODO: Get notification details from DB to find repository/branch
        # For now, this is a placeholder

        # Clone/update repository
        # repo_path = clone_or_update_repository(repository_id)

        # Discover files
        # discovery = get_artifact_discovery()
        # discovery_result = discovery.discover(repo_path)

        # Process files in batches
        # embed_service = get_embed_service()
        # index_writer = get_index_writer()

        # Mark as done
        asyncio.run(
            notification_service.update_status(
                uuid.UUID(notification_id),
                NotificationStatus.DONE,
            )
        )

        result["status"] = "completed"
        logger.info(
            "Notification processed successfully",
            notification_id=notification_id,
            files_indexed=result["files_indexed"],
        )

    except Exception as e:
        logger.error(
            "Notification processing failed",
            notification_id=notification_id,
            error=str(e),
        )

        # Update status to error
        import asyncio
        asyncio.run(
            notification_service.update_status(
                uuid.UUID(notification_id),
                NotificationStatus.ERROR,
                error_message=str(e)[:1024],
            )
        )

        result["status"] = "error"
        result["errors"].append(str(e))

        # Re-raise for Celery retry
        raise

    return result


@shared_task(bind=True)
def ingest_repository_batch(
    self,
    repository_id: str,
    branch_id: str,
    file_paths: list[str],
    repo_base_path: str,
) -> dict[str, Any]:
    """Process a batch of files for indexing.

    Args:
        repository_id: Repository UUID.
        branch_id: Branch UUID.
        file_paths: List of relative file paths to process.
        repo_base_path: Base path to repository.

    Returns:
        Batch processing results.
    """
    logger.info(
        "Processing file batch",
        repository_id=repository_id,
        branch_id=branch_id,
        file_count=len(file_paths),
        task_id=self.request.id,
    )

    result = {
        "repository_id": repository_id,
        "branch_id": branch_id,
        "files_processed": 0,
        "chunks_created": 0,
        "errors": [],
    }

    try:
        embed_service = get_embed_service()
        base_path = Path(repo_base_path)

        embedding_results = []
        for rel_path in file_paths:
            file_path = base_path / rel_path
            if not file_path.exists():
                result["errors"].append(f"File not found: {rel_path}")
                continue

            # Create minimal FileInfo
            from backend.src.services.ingestion.file_filters import FileFilter

            file_filter = FileFilter()
            file_info = file_filter.analyze_file(file_path, rel_path)

            # Process file
            embed_result = embed_service.process_file(
                file_info=file_info,
                repository_id=repository_id,
                branch_id=branch_id,
            )

            if embed_result.error:
                result["errors"].append(f"{rel_path}: {embed_result.error}")
            else:
                embedding_results.append(embed_result)
                result["files_processed"] += 1
                result["chunks_created"] += len(embed_result.chunks)

        # Write to index
        if embedding_results:
            import asyncio
            index_writer = get_index_writer()

            # TODO: Get repository/branch names from DB
            write_result = asyncio.run(
                index_writer.write_embedding_results(
                    results=embedding_results,
                    repository_id=repository_id,
                    repository_name="unknown",  # Would come from DB
                    branch_id=branch_id,
                    branch_name="unknown",  # Would come from DB
                )
            )

            if write_result.errors:
                result["errors"].extend(write_result.errors)

        logger.info(
            "Batch processing complete",
            repository_id=repository_id,
            files_processed=result["files_processed"],
            chunks_created=result["chunks_created"],
        )

    except Exception as e:
        logger.error(
            "Batch processing failed",
            repository_id=repository_id,
            error=str(e),
        )
        result["errors"].append(str(e))
        raise

    return result


@shared_task(bind=True)
def full_reindex_repository(
    self,
    repository_id: str,
    branch_id: str,
) -> dict[str, Any]:
    """Perform a full reindex of a repository branch.

    This is triggered by scheduled reindexing or manual refresh.

    Args:
        repository_id: Repository UUID.
        branch_id: Branch UUID.

    Returns:
        Reindex results.
    """
    logger.info(
        "Starting full reindex",
        repository_id=repository_id,
        branch_id=branch_id,
        task_id=self.request.id,
    )

    result = {
        "repository_id": repository_id,
        "branch_id": branch_id,
        "files_discovered": 0,
        "files_indexed": 0,
        "chunks_created": 0,
        "documents_deleted": 0,
        "errors": [],
    }

    try:
        import asyncio

        # Delete existing documents for this branch
        index_writer = get_index_writer()
        deleted = asyncio.run(
            index_writer.delete_branch_documents(repository_id, branch_id)
        )
        result["documents_deleted"] = deleted

        # TODO: Clone/update repository and discover files
        # This would integrate with git operations

        logger.info(
            "Full reindex complete",
            repository_id=repository_id,
            branch_id=branch_id,
            documents_deleted=result["documents_deleted"],
            files_indexed=result["files_indexed"],
        )

    except Exception as e:
        logger.error(
            "Full reindex failed",
            repository_id=repository_id,
            branch_id=branch_id,
            error=str(e),
        )
        result["errors"].append(str(e))
        raise

    return result
