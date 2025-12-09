"""Celery tasks for ingestion pipeline."""

import asyncio
import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, TypeVar

from celery import shared_task

from backend.src.config.constants import MAX_BATCH_SIZE
from backend.src.config.logging import get_logger
from backend.src.models.notification import NotificationStatus
from backend.src.services.git.operations import get_git_operations_service
from backend.src.services.ingestion.discover import get_artifact_discovery
from backend.src.services.ingestion.embed import get_embed_service
from backend.src.services.ingestion.index_writer import get_index_writer
from backend.src.services.repository_service import (
    get_notification_service,
    get_repository_service,
)

T = TypeVar("T")


def batched(iterable: Iterable[T], n: int) -> Iterator[tuple[T, ...]]:
    """Batch an iterable into chunks of size n.

    This is a backport of itertools.batched from Python 3.12.

    Args:
        iterable: The iterable to batch.
        n: The batch size.

    Yields:
        Tuples of at most n items.
    """
    from itertools import islice

    if n < 1:
        raise ValueError("n must be at least 1")
    iterator = iter(iterable)
    while batch := tuple(islice(iterator, n)):
        yield batch


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
        asyncio.run(
            notification_service.update_status(
                uuid.UUID(notification_id),
                NotificationStatus.PROCESSING,
            )
        )

        # Get notification details from DB to find repository/branch
        notification = asyncio.run(
            notification_service.get_notification(uuid.UUID(notification_id))
        )
        if notification is None:
            raise ValueError(f"Notification not found: {notification_id}")

        repository_id = str(notification.repository_id)
        branch_id = str(notification.branch_id) if notification.branch_id else None

        logger.info(
            "Retrieved notification details",
            notification_id=notification_id,
            repository_id=repository_id,
            branch_id=branch_id,
        )

        # Get repository details for cloning
        repository_service = get_repository_service()
        repository = asyncio.run(
            repository_service.get_repository(notification.repository_id)
        )
        if repository is None:
            raise ValueError(f"Repository not found: {repository_id}")

        # Get branch details
        branch = None
        branch_name = None
        if branch_id:
            branch = asyncio.run(repository_service.get_branch(uuid.UUID(branch_id)))
            branch_name = branch.name if branch else repository.default_branch
        else:
            branch_name = repository.default_branch

        # Clone/update repository
        git_service = get_git_operations_service()
        credentials = repository_service.get_git_credentials(repository)

        clone_result = git_service.clone_or_update_repository(
            git_url=repository.git_url,
            repository_id=repository_id,
            branch=branch_name,
            credentials=credentials,
        )

        if not clone_result.success:
            raise RuntimeError(f"Git operation failed: {clone_result.error}")

        repo_path = clone_result.repo_path
        result["commit_sha"] = clone_result.commit_sha

        logger.info(
            "Repository ready for indexing",
            repository_id=repository_id,
            repo_path=str(repo_path),
            commit_sha=clone_result.commit_sha,
        )

        # Discover files
        discovery = get_artifact_discovery()
        discovery_result = discovery.discover(repo_path)

        logger.info(
            "Files discovered",
            repository_id=repository_id,
            files_to_index=len(discovery_result.files_to_index),
            files_skipped=discovery_result.files_skipped,
        )

        # Process files in batches
        for batch in batched(discovery_result.files_to_index, MAX_BATCH_SIZE):
            file_paths = [f.relative_path for f in batch]
            ingest_repository_batch.delay(
                repository_id=repository_id,
                branch_id=branch_id or "",
                file_paths=file_paths,
                repo_base_path=str(repo_path),
            )
            result["files_indexed"] += len(file_paths)

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
            repository_id=repository_id,
            files_indexed=result["files_indexed"],
        )

    except Exception as e:
        logger.error(
            "Notification processing failed",
            notification_id=notification_id,
            error=str(e),
        )

        # Update status to error
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
            index_writer = get_index_writer()

            # Get repository/branch names from DB
            repository_service = get_repository_service()
            repository = repository_service.get_repository_sync(
                uuid.UUID(repository_id)
            )
            repository_name = repository.name if repository else "unknown"

            branch = repository_service.get_branch_sync(uuid.UUID(branch_id))
            branch_name = branch.name if branch else "unknown"

            write_result = asyncio.run(
                index_writer.write_embedding_results(
                    results=embedding_results,
                    repository_id=repository_id,
                    repository_name=repository_name,
                    branch_id=branch_id,
                    branch_name=branch_name,
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
        # Delete existing documents for this branch
        index_writer = get_index_writer()
        deleted = asyncio.run(
            index_writer.delete_branch_documents(repository_id, branch_id)
        )
        result["documents_deleted"] = deleted

        # Get repository details for cloning
        repository_service = get_repository_service()
        repository = repository_service.get_repository_sync(uuid.UUID(repository_id))
        if repository is None:
            raise ValueError(f"Repository not found: {repository_id}")

        branch = repository_service.get_branch_sync(uuid.UUID(branch_id))
        if branch is None:
            raise ValueError(f"Branch not found: {branch_id}")

        # Clone/update repository
        git_service = get_git_operations_service()
        credentials = repository_service.get_git_credentials(repository)

        clone_result = git_service.clone_or_update_repository(
            git_url=repository.git_url,
            repository_id=repository_id,
            branch=branch.name,
            credentials=credentials,
        )

        if not clone_result.success:
            raise RuntimeError(f"Git operation failed: {clone_result.error}")

        repo_path = clone_result.repo_path
        result["commit_sha"] = clone_result.commit_sha

        logger.info(
            "Repository ready for reindexing",
            repository_id=repository_id,
            repo_path=str(repo_path),
            commit_sha=clone_result.commit_sha,
        )

        # Discover files to index
        discovery = get_artifact_discovery()
        discovery_result = discovery.discover(repo_path, branch=branch.name)
        result["files_discovered"] = len(discovery_result.files_to_index)

        # Process files in batches
        for batch in batched(discovery_result.files_to_index, MAX_BATCH_SIZE):
            file_paths = [f.relative_path for f in batch]
            ingest_repository_batch.delay(
                repository_id=repository_id,
                branch_id=branch_id,
                file_paths=file_paths,
                repo_base_path=str(repo_path),
            )
            result["files_indexed"] += len(file_paths)

        logger.info(
            "Full reindex complete",
            repository_id=repository_id,
            branch_id=branch_id,
            repository_name=repository.name,
            branch_name=branch.name,
            documents_deleted=result["documents_deleted"],
            files_discovered=result["files_discovered"],
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
