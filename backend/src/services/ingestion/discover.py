"""Artifact discovery for repository ingestion."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from backend.src.config.constants import MAX_BATCH_SIZE
from backend.src.config.logging import get_logger
from backend.src.services.ingestion.file_filters import (
    FileFilter,
    FileInfo,
    IndexAction,
    get_file_filter,
)

logger = get_logger(__name__)


@dataclass
class DiscoveryResult:
    """Result of artifact discovery."""

    files_to_index: list[FileInfo] = field(default_factory=list)
    files_catalog_only: list[FileInfo] = field(default_factory=list)
    files_skipped: int = 0
    directories_skipped: int = 0
    total_size_bytes: int = 0
    errors: list[str] = field(default_factory=list)


class ArtifactDiscovery:
    """Discover and filter artifacts in a repository."""

    def __init__(
        self,
        file_filter: FileFilter | None = None,
        batch_size: int = MAX_BATCH_SIZE,
    ):
        """Initialize artifact discovery.

        Args:
            file_filter: File filter instance.
            batch_size: Maximum files per batch.
        """
        self.file_filter = file_filter or get_file_filter()
        self.batch_size = batch_size

    def discover(
        self,
        repo_path: Path,
        branch: str | None = None,
    ) -> DiscoveryResult:
        """Discover all indexable artifacts in a repository.

        Args:
            repo_path: Path to repository root.
            branch: Branch name for logging (optional).

        Returns:
            DiscoveryResult with categorized files.
        """
        logger.info(
            "Starting artifact discovery",
            repo_path=str(repo_path),
            branch=branch,
        )

        result = DiscoveryResult()

        if not repo_path.exists():
            result.errors.append(f"Repository path does not exist: {repo_path}")
            return result

        if not repo_path.is_dir():
            result.errors.append(f"Repository path is not a directory: {repo_path}")
            return result

        self._walk_directory(repo_path, repo_path, result)

        logger.info(
            "Artifact discovery complete",
            files_to_index=len(result.files_to_index),
            files_catalog_only=len(result.files_catalog_only),
            files_skipped=result.files_skipped,
            directories_skipped=result.directories_skipped,
            total_size_bytes=result.total_size_bytes,
        )

        return result

    def _walk_directory(
        self,
        base_path: Path,
        current_path: Path,
        result: DiscoveryResult,
    ) -> None:
        """Recursively walk directory and discover files.

        Args:
            base_path: Repository root path.
            current_path: Current directory being walked.
            result: Result accumulator.
        """
        try:
            entries = list(current_path.iterdir())
        except PermissionError as e:
            result.errors.append(f"Permission denied: {current_path}")
            logger.warning("Permission denied", path=str(current_path))
            return
        except OSError as e:
            result.errors.append(f"OS error reading {current_path}: {e}")
            logger.warning("OS error", path=str(current_path), error=str(e))
            return

        for entry in entries:
            try:
                if entry.is_dir():
                    # Check if we should skip this directory
                    if self.file_filter.should_skip_directory(entry.name):
                        result.directories_skipped += 1
                        logger.debug("Skipping directory", name=entry.name)
                        continue

                    # Recurse into subdirectory
                    self._walk_directory(base_path, entry, result)

                elif entry.is_file():
                    # Analyze file
                    relative_path = str(entry.relative_to(base_path))
                    file_info = self.file_filter.analyze_file(entry, relative_path)

                    result.total_size_bytes += file_info.size_bytes

                    if file_info.action == IndexAction.FULL_INDEX:
                        result.files_to_index.append(file_info)
                    elif file_info.action == IndexAction.CATALOG_ONLY:
                        result.files_catalog_only.append(file_info)
                    else:
                        result.files_skipped += 1

            except OSError as e:
                result.errors.append(f"Error processing {entry}: {e}")
                logger.warning("Error processing entry", path=str(entry), error=str(e))

    def get_batches(
        self,
        files: list[FileInfo],
    ) -> list[list[FileInfo]]:
        """Split files into batches for processing.

        Args:
            files: List of files to batch.

        Returns:
            List of file batches.
        """
        batches = []
        for i in range(0, len(files), self.batch_size):
            batches.append(files[i : i + self.batch_size])
        return batches


# Service singleton
_discovery_service: ArtifactDiscovery | None = None


def get_artifact_discovery() -> ArtifactDiscovery:
    """Get artifact discovery service singleton."""
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = ArtifactDiscovery()
    return _discovery_service
