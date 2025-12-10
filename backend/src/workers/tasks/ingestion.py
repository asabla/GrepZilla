"""Celery tasks for ingestion pipeline."""

import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, TypeVar

from celery import shared_task

from backend.src.config.constants import MAX_BATCH_SIZE
from backend.src.config.logging import get_logger
from backend.src.models.branch import FreshnessStatus
from backend.src.models.notification import NotificationStatus
from backend.src.models.repository import AccessState
from backend.src.services.git.operations import get_git_operations_service
from backend.src.services.ingestion.artifact_writer import get_artifact_writer
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
        notification_service.update_status_sync(
            uuid.UUID(notification_id),
            NotificationStatus.PROCESSING,
        )

        # Get notification details from DB to find repository/branch
        notification = notification_service.get_notification_sync(
            uuid.UUID(notification_id)
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
        repository = repository_service.get_repository_sync(notification.repository_id)
        if repository is None:
            raise ValueError(f"Repository not found: {repository_id}")

        # Get branch details
        branch = None
        branch_name = None
        if branch_id:
            branch = repository_service.get_branch_sync(uuid.UUID(branch_id))
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
            files_catalog_only=len(discovery_result.files_catalog_only),
            files_skipped=discovery_result.files_skipped,
        )

        # Write all discovered files to artifacts index (DB + Meilisearch)
        if branch_id:
            all_discovered_files = (
                discovery_result.files_to_index + discovery_result.files_catalog_only
            )
            if all_discovered_files:
                artifact_writer = get_artifact_writer()
                artifact_result = artifact_writer.write_artifacts_sync(
                    files=all_discovered_files,
                    repository_id=repository_id,
                    branch_id=branch_id,
                    commit_sha=clone_result.commit_sha,
                    mark_as_parsed=False,  # Will be marked after chunk processing
                )
                result["artifacts_written"] = artifact_result.artifacts_written
                if artifact_result.errors:
                    result["errors"].extend(artifact_result.errors)

                logger.info(
                    "Artifacts written",
                    repository_id=repository_id,
                    artifacts_written=artifact_result.artifacts_written,
                    meilisearch_indexed=artifact_result.meilisearch_indexed,
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
        notification_service.update_status_sync(
            uuid.UUID(notification_id),
            NotificationStatus.DONE,
        )

        # Update branch freshness after successful notification processing
        if branch_id:
            repository_service = get_repository_service()
            repository_service.update_branch_freshness_sync(
                uuid.UUID(branch_id),
                FreshnessStatus.FRESH,
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
        notification_service.update_status_sync(
            uuid.UUID(notification_id),
            NotificationStatus.ERROR,
            error_message=str(e)[:1024],
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

            branch_name = "unknown"
            if branch_id:
                branch = repository_service.get_branch_sync(uuid.UUID(branch_id))
                branch_name = branch.name if branch else "unknown"

            write_result = index_writer.write_embedding_results_sync(
                results=embedding_results,
                repository_id=repository_id,
                repository_name=repository_name,
                branch_id=branch_id,
                branch_name=branch_name,
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
        "artifacts_deleted": 0,
        "artifacts_written": 0,
        "errors": [],
    }

    try:
        # Delete existing documents for this branch (chunks index)
        index_writer = get_index_writer()
        deleted = index_writer.delete_branch_documents_sync(repository_id, branch_id)
        result["documents_deleted"] = deleted

        # Delete existing artifacts for this branch (artifacts index + DB)
        artifact_writer = get_artifact_writer()
        artifacts_deleted = artifact_writer.delete_branch_artifacts_sync(
            repository_id, branch_id
        )
        result["artifacts_deleted"] = artifacts_deleted

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

        # Write all discovered files to artifacts index (DB + Meilisearch)
        all_discovered_files = (
            discovery_result.files_to_index + discovery_result.files_catalog_only
        )
        if all_discovered_files:
            artifact_result = artifact_writer.write_artifacts_sync(
                files=all_discovered_files,
                repository_id=repository_id,
                branch_id=branch_id,
                commit_sha=clone_result.commit_sha,
                mark_as_parsed=False,
            )
            result["artifacts_written"] = artifact_result.artifacts_written
            if artifact_result.errors:
                result["errors"].extend(artifact_result.errors)

            logger.info(
                "Artifacts written during reindex",
                repository_id=repository_id,
                artifacts_written=artifact_result.artifacts_written,
            )

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

        # Mark repository as active after successful indexing
        repository_service.update_access_state_sync(
            uuid.UUID(repository_id),
            AccessState.ACTIVE,
        )

        # Mark branch as fresh after successful indexing
        repository_service.update_branch_freshness_sync(
            uuid.UUID(branch_id),
            FreshnessStatus.FRESH,
        )

    except Exception as e:
        logger.error(
            "Full reindex failed",
            repository_id=repository_id,
            branch_id=branch_id,
            error=str(e),
        )
        result["errors"].append(str(e))

        # Mark repository as error state on failure
        try:
            repository_service = get_repository_service()
            repository_service.update_access_state_sync(
                uuid.UUID(repository_id),
                AccessState.ERROR,
            )
            # Also mark branch as error
            repository_service.update_branch_freshness_sync(
                uuid.UUID(branch_id),
                FreshnessStatus.ERROR,
            )
        except Exception as state_error:
            logger.error(
                "Failed to update repository/branch state to ERROR",
                repository_id=repository_id,
                branch_id=branch_id,
                error=str(state_error),
            )

        raise

    return result
