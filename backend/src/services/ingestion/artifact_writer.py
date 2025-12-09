"""Artifact writer for persisting file metadata to DB and Meilisearch."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.src.config.logging import get_logger
from backend.src.db.session import get_session_context, get_sync_session_context
from backend.src.models.artifact import Artifact, FileType, ParseStatus
from backend.src.services.ingestion.file_filters import (
    FileCategory,
    FileInfo,
    IndexAction,
)
from backend.src.services.search.index_client import (
    ARTIFACTS_INDEX,
    MeilisearchClient,
    get_meilisearch_client,
)

logger = get_logger(__name__)


@dataclass
class ArtifactDocument:
    """Document representing a file artifact for Meilisearch."""

    id: str
    repository_id: str
    branch_id: str
    path: str
    file_type: str
    size_bytes: int
    parse_status: str
    last_indexed_at: str


@dataclass
class ArtifactWriteResult:
    """Result of an artifact write operation."""

    artifacts_written: int = 0
    artifacts_failed: int = 0
    db_upserted: int = 0
    meilisearch_indexed: int = 0
    errors: list[str] = field(default_factory=list)


def _file_category_to_file_type(category: FileCategory) -> FileType:
    """Convert FileCategory to FileType enum.

    Args:
        category: File category from filtering.

    Returns:
        Corresponding FileType for DB storage.
    """
    mapping = {
        FileCategory.CODE: FileType.CODE,
        FileCategory.DOCUMENTATION: FileType.DOC,
        FileCategory.CONFIGURATION: FileType.CONFIG,
        FileCategory.BINARY: FileType.BINARY,
        FileCategory.UNKNOWN: FileType.OTHER,
    }
    return mapping.get(category, FileType.OTHER)


def _index_action_to_parse_status(action: IndexAction) -> ParseStatus:
    """Convert IndexAction to ParseStatus enum.

    Args:
        action: Index action from filtering.

    Returns:
        Corresponding ParseStatus for DB storage.
    """
    if action == IndexAction.FULL_INDEX:
        return ParseStatus.PARSED
    elif action == IndexAction.CATALOG_ONLY:
        return ParseStatus.SKIPPED
    else:
        return ParseStatus.SKIPPED


class ArtifactWriter:
    """Write artifact metadata to database and Meilisearch index."""

    def __init__(
        self,
        client: MeilisearchClient | None = None,
        index_name: str | None = None,
    ):
        """Initialize artifact writer.

        Args:
            client: Meilisearch client instance.
            index_name: Name of the index to write to. Defaults to ARTIFACTS_INDEX.
        """
        self.client = client or get_meilisearch_client()
        self.index_name = index_name or ARTIFACTS_INDEX

    async def write_artifacts(
        self,
        files: list[FileInfo],
        repository_id: str,
        branch_id: str,
        commit_sha: str | None = None,
        mark_as_parsed: bool = False,
    ) -> ArtifactWriteResult:
        """Write artifact metadata for discovered files.

        This writes both to the PostgreSQL artifacts table and to the
        Meilisearch artifacts index for searchability.

        Args:
            files: List of FileInfo from discovery.
            repository_id: Repository UUID string.
            branch_id: Branch UUID string.
            commit_sha: Optional commit SHA for last_seen_commit.
            mark_as_parsed: If True, mark FULL_INDEX files as parsed.

        Returns:
            ArtifactWriteResult with counts and errors.
        """
        result = ArtifactWriteResult()
        indexed_at = datetime.now(timezone.utc)

        if not files:
            logger.debug("No artifacts to write")
            return result

        logger.info(
            "Writing artifacts",
            repository_id=repository_id,
            branch_id=branch_id,
            file_count=len(files),
        )

        # Prepare DB records and Meilisearch documents
        db_records = []
        meilisearch_docs = []
        repo_uuid = uuid.UUID(repository_id)
        branch_uuid = uuid.UUID(branch_id)

        for file_info in files:
            file_type = _file_category_to_file_type(file_info.category)
            parse_status = _index_action_to_parse_status(file_info.action)

            # If mark_as_parsed is True and the file was fully indexed, mark as parsed
            if mark_as_parsed and file_info.action == IndexAction.FULL_INDEX:
                parse_status = ParseStatus.PARSED

            # Generate deterministic ID based on repo + branch + path
            artifact_id = uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"{repository_id}:{branch_id}:{file_info.relative_path}",
            )

            db_record = {
                "id": artifact_id,
                "repository_id": repo_uuid,
                "branch_id": branch_uuid,
                "path": file_info.relative_path,
                "file_type": file_type,
                "size_bytes": file_info.size_bytes,
                "parse_status": parse_status,
                "has_line_map": file_info.action == IndexAction.FULL_INDEX,
                "last_seen_commit": commit_sha,
                "last_indexed_at": indexed_at
                if file_info.action == IndexAction.FULL_INDEX
                else None,
                "updated_at": indexed_at,
            }
            db_records.append(db_record)

            meilisearch_doc = {
                "id": str(artifact_id),
                "repository_id": repository_id,
                "branch_id": branch_id,
                "path": file_info.relative_path,
                "file_type": file_type.value,
                "size_bytes": file_info.size_bytes,
                "parse_status": parse_status.value,
                "last_indexed_at": indexed_at.isoformat()
                if file_info.action == IndexAction.FULL_INDEX
                else None,
            }
            meilisearch_docs.append(meilisearch_doc)

        # Write to database
        try:
            db_upserted = await self._upsert_to_db(db_records)
            result.db_upserted = db_upserted
            logger.debug("DB upsert complete", count=db_upserted)
        except Exception as e:
            result.errors.append(f"DB upsert failed: {e}")
            logger.error("DB upsert failed", error=str(e))

        # Write to Meilisearch in batches
        batch_size = 100
        for i in range(0, len(meilisearch_docs), batch_size):
            batch = meilisearch_docs[i : i + batch_size]
            try:
                await self._write_meilisearch_batch(batch)
                result.meilisearch_indexed += len(batch)
            except Exception as e:
                result.artifacts_failed += len(batch)
                result.errors.append(f"Meilisearch batch write failed: {e}")
                logger.error(
                    "Meilisearch batch write failed",
                    batch_start=i,
                    batch_size=len(batch),
                    error=str(e),
                )

        result.artifacts_written = result.db_upserted

        logger.info(
            "Artifact write complete",
            artifacts_written=result.artifacts_written,
            db_upserted=result.db_upserted,
            meilisearch_indexed=result.meilisearch_indexed,
            errors=len(result.errors),
        )

        return result

    async def _upsert_to_db(self, records: list[dict]) -> int:
        """Upsert artifact records to PostgreSQL.

        Args:
            records: List of artifact record dicts.

        Returns:
            Number of records upserted.
        """
        if not records:
            return 0

        async with get_session_context() as session:
            # Use PostgreSQL upsert (INSERT ... ON CONFLICT)
            stmt = insert(Artifact).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "path": stmt.excluded.path,
                    "file_type": stmt.excluded.file_type,
                    "size_bytes": stmt.excluded.size_bytes,
                    "parse_status": stmt.excluded.parse_status,
                    "has_line_map": stmt.excluded.has_line_map,
                    "last_seen_commit": stmt.excluded.last_seen_commit,
                    "last_indexed_at": stmt.excluded.last_indexed_at,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)

        return len(records)

    async def _write_meilisearch_batch(self, documents: list[dict]) -> None:
        """Write a batch of documents to Meilisearch.

        Args:
            documents: List of artifact documents.

        Raises:
            Exception: If write fails.
        """
        await self.client.add_documents(self.index_name, documents)

    async def delete_branch_artifacts(
        self,
        repository_id: str,
        branch_id: str,
    ) -> int:
        """Delete all artifacts for a branch (before reindex).

        Args:
            repository_id: Repository UUID.
            branch_id: Branch UUID.

        Returns:
            Number of artifacts deleted from Meilisearch.
        """
        logger.info(
            "Deleting branch artifacts",
            repository_id=repository_id,
            branch_id=branch_id,
        )

        # Delete from Meilisearch
        filter_str = f"repository_id = '{repository_id}' AND branch_id = '{branch_id}'"
        deleted = await self.client.delete_documents_by_filter(
            self.index_name, filter_str
        )

        # Delete from DB
        async with get_session_context() as session:
            repo_uuid = uuid.UUID(repository_id)
            branch_uuid = uuid.UUID(branch_id)

            stmt = select(Artifact).where(
                Artifact.repository_id == repo_uuid,
                Artifact.branch_id == branch_uuid,
            )
            result = await session.execute(stmt)
            artifacts = result.scalars().all()

            for artifact in artifacts:
                await session.delete(artifact)

            db_deleted = len(artifacts)

        logger.info(
            "Branch artifacts deleted",
            repository_id=repository_id,
            branch_id=branch_id,
            meilisearch_deleted=deleted,
            db_deleted=db_deleted,
        )

        return deleted

    async def mark_artifacts_parsed(
        self,
        repository_id: str,
        branch_id: str,
        file_paths: list[str],
    ) -> int:
        """Mark specific artifacts as successfully parsed.

        Called after chunk embedding is complete for a batch.

        Args:
            repository_id: Repository UUID.
            branch_id: Branch UUID.
            file_paths: List of relative file paths that were parsed.

        Returns:
            Number of artifacts updated.
        """
        if not file_paths:
            return 0

        indexed_at = datetime.now(timezone.utc)
        repo_uuid = uuid.UUID(repository_id)
        branch_uuid = uuid.UUID(branch_id)

        async with get_session_context() as session:
            stmt = select(Artifact).where(
                Artifact.repository_id == repo_uuid,
                Artifact.branch_id == branch_uuid,
                Artifact.path.in_(file_paths),
            )
            result = await session.execute(stmt)
            artifacts = result.scalars().all()

            for artifact in artifacts:
                artifact.parse_status = ParseStatus.PARSED
                artifact.last_indexed_at = indexed_at
                artifact.has_line_map = True

            logger.debug(
                "Marked artifacts as parsed",
                repository_id=repository_id,
                branch_id=branch_id,
                count=len(artifacts),
            )

            return len(artifacts)

    # =========================================================================
    # Synchronous methods for Celery workers
    # =========================================================================

    def write_artifacts_sync(
        self,
        files: list[FileInfo],
        repository_id: str,
        branch_id: str,
        commit_sha: str | None = None,
        mark_as_parsed: bool = False,
    ) -> ArtifactWriteResult:
        """Write artifact metadata (synchronous version for workers).

        This writes both to the PostgreSQL artifacts table and to the
        Meilisearch artifacts index for searchability.

        Args:
            files: List of FileInfo from discovery.
            repository_id: Repository UUID string.
            branch_id: Branch UUID string.
            commit_sha: Optional commit SHA for last_seen_commit.
            mark_as_parsed: If True, mark FULL_INDEX files as parsed.

        Returns:
            ArtifactWriteResult with counts and errors.
        """
        result = ArtifactWriteResult()
        indexed_at = datetime.now(timezone.utc)

        if not files:
            logger.debug("No artifacts to write")
            return result

        logger.info(
            "Writing artifacts (sync)",
            repository_id=repository_id,
            branch_id=branch_id,
            file_count=len(files),
        )

        # Prepare DB records and Meilisearch documents
        db_records = []
        meilisearch_docs = []
        repo_uuid = uuid.UUID(repository_id)
        branch_uuid = uuid.UUID(branch_id)

        for file_info in files:
            file_type = _file_category_to_file_type(file_info.category)
            parse_status = _index_action_to_parse_status(file_info.action)

            # If mark_as_parsed is True and the file was fully indexed, mark as parsed
            if mark_as_parsed and file_info.action == IndexAction.FULL_INDEX:
                parse_status = ParseStatus.PARSED

            # Generate deterministic ID based on repo + branch + path
            artifact_id = uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"{repository_id}:{branch_id}:{file_info.relative_path}",
            )

            db_record = {
                "id": artifact_id,
                "repository_id": repo_uuid,
                "branch_id": branch_uuid,
                "path": file_info.relative_path,
                "file_type": file_type,
                "size_bytes": file_info.size_bytes,
                "parse_status": parse_status,
                "has_line_map": file_info.action == IndexAction.FULL_INDEX,
                "last_seen_commit": commit_sha,
                "last_indexed_at": indexed_at
                if file_info.action == IndexAction.FULL_INDEX
                else None,
                "updated_at": indexed_at,
            }
            db_records.append(db_record)

            meilisearch_doc = {
                "id": str(artifact_id),
                "repository_id": repository_id,
                "branch_id": branch_id,
                "path": file_info.relative_path,
                "file_type": file_type.value,
                "size_bytes": file_info.size_bytes,
                "parse_status": parse_status.value,
                "last_indexed_at": indexed_at.isoformat()
                if file_info.action == IndexAction.FULL_INDEX
                else None,
            }
            meilisearch_docs.append(meilisearch_doc)

        # Write to database
        try:
            db_upserted = self._upsert_to_db_sync(db_records)
            result.db_upserted = db_upserted
            logger.debug("DB upsert complete (sync)", count=db_upserted)
        except Exception as e:
            result.errors.append(f"DB upsert failed: {e}")
            logger.error("DB upsert failed (sync)", error=str(e))

        # Write to Meilisearch in batches
        batch_size = 100
        for i in range(0, len(meilisearch_docs), batch_size):
            batch = meilisearch_docs[i : i + batch_size]
            try:
                self._write_meilisearch_batch_sync(batch)
                result.meilisearch_indexed += len(batch)
            except Exception as e:
                result.artifacts_failed += len(batch)
                result.errors.append(f"Meilisearch batch write failed: {e}")
                logger.error(
                    "Meilisearch batch write failed (sync)",
                    batch_start=i,
                    batch_size=len(batch),
                    error=str(e),
                )

        result.artifacts_written = result.db_upserted

        logger.info(
            "Artifact write complete (sync)",
            artifacts_written=result.artifacts_written,
            db_upserted=result.db_upserted,
            meilisearch_indexed=result.meilisearch_indexed,
            errors=len(result.errors),
        )

        return result

    def _upsert_to_db_sync(self, records: list[dict]) -> int:
        """Upsert artifact records to PostgreSQL (synchronous).

        Args:
            records: List of artifact record dicts.

        Returns:
            Number of records upserted.
        """
        if not records:
            return 0

        with get_sync_session_context() as session:
            # Use PostgreSQL upsert (INSERT ... ON CONFLICT)
            stmt = insert(Artifact).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "path": stmt.excluded.path,
                    "file_type": stmt.excluded.file_type,
                    "size_bytes": stmt.excluded.size_bytes,
                    "parse_status": stmt.excluded.parse_status,
                    "has_line_map": stmt.excluded.has_line_map,
                    "last_seen_commit": stmt.excluded.last_seen_commit,
                    "last_indexed_at": stmt.excluded.last_indexed_at,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            session.execute(stmt)
            session.commit()

        return len(records)

    def _write_meilisearch_batch_sync(self, documents: list[dict]) -> None:
        """Write a batch of documents to Meilisearch (synchronous).

        Args:
            documents: List of artifact documents.

        Raises:
            Exception: If write fails.
        """
        self.client.add_documents_sync(self.index_name, documents)

    def delete_branch_artifacts_sync(
        self,
        repository_id: str,
        branch_id: str,
    ) -> int:
        """Delete all artifacts for a branch (synchronous version).

        Args:
            repository_id: Repository UUID.
            branch_id: Branch UUID.

        Returns:
            Number of artifacts deleted from Meilisearch.
        """
        logger.info(
            "Deleting branch artifacts (sync)",
            repository_id=repository_id,
            branch_id=branch_id,
        )

        # Delete from Meilisearch
        filter_str = f"repository_id = '{repository_id}' AND branch_id = '{branch_id}'"
        deleted = self.client.delete_documents_by_filter_sync(
            self.index_name, filter_str
        )

        # Delete from DB
        with get_sync_session_context() as session:
            repo_uuid = uuid.UUID(repository_id)
            branch_uuid = uuid.UUID(branch_id)

            stmt = select(Artifact).where(
                Artifact.repository_id == repo_uuid,
                Artifact.branch_id == branch_uuid,
            )
            result = session.execute(stmt)
            artifacts = result.scalars().all()

            for artifact in artifacts:
                session.delete(artifact)

            session.commit()
            db_deleted = len(artifacts)

        logger.info(
            "Branch artifacts deleted (sync)",
            repository_id=repository_id,
            branch_id=branch_id,
            meilisearch_deleted=deleted,
            db_deleted=db_deleted,
        )

        return deleted


# Service singleton
_artifact_writer: ArtifactWriter | None = None


def get_artifact_writer() -> ArtifactWriter:
    """Get artifact writer singleton."""
    global _artifact_writer
    if _artifact_writer is None:
        _artifact_writer = ArtifactWriter()
    return _artifact_writer
