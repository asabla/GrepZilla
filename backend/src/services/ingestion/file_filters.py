"""File filtering utilities for ingestion pipeline."""

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from backend.src.config.constants import (
    BINARY_EXTENSIONS,
    CATALOG_ONLY_SIZE_THRESHOLD,
    CODE_EXTENSIONS,
    CONFIG_EXTENSIONS,
    DOC_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    MAX_PATH_LENGTH,
    SKIP_DIRECTORIES,
)
from backend.src.config.logging import get_logger

logger = get_logger(__name__)


class FileCategory(StrEnum):
    """Category of a file for indexing."""

    CODE = "code"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    BINARY = "binary"
    UNKNOWN = "unknown"


class IndexAction(StrEnum):
    """Action to take for a file during ingestion."""

    FULL_INDEX = "full_index"  # Parse and create searchable chunks
    CATALOG_ONLY = "catalog_only"  # Just record file metadata
    SKIP = "skip"  # Ignore entirely


@dataclass
class FileInfo:
    """Information about a file for ingestion decisions."""

    path: Path
    relative_path: str
    size_bytes: int
    extension: str
    category: FileCategory
    action: IndexAction


class FileFilter:
    """Filter and categorize files for ingestion."""

    def __init__(
        self,
        max_file_size: int = MAX_FILE_SIZE_BYTES,
        catalog_threshold: int = CATALOG_ONLY_SIZE_THRESHOLD,
        max_path_length: int = MAX_PATH_LENGTH,
        skip_directories: frozenset[str] = SKIP_DIRECTORIES,
        code_extensions: frozenset[str] = CODE_EXTENSIONS,
        doc_extensions: frozenset[str] = DOC_EXTENSIONS,
        config_extensions: frozenset[str] = CONFIG_EXTENSIONS,
        binary_extensions: frozenset[str] = BINARY_EXTENSIONS,
    ):
        """Initialize file filter.

        Args:
            max_file_size: Maximum size for full indexing.
            catalog_threshold: Threshold for catalog-only treatment.
            max_path_length: Maximum file path length.
            skip_directories: Directories to skip entirely.
            code_extensions: Extensions to treat as code.
            doc_extensions: Extensions to treat as documentation.
            config_extensions: Extensions to treat as configuration.
            binary_extensions: Extensions to skip as binary.
        """
        self.max_file_size = max_file_size
        self.catalog_threshold = catalog_threshold
        self.max_path_length = max_path_length
        self.skip_directories = skip_directories
        self.code_extensions = code_extensions
        self.doc_extensions = doc_extensions
        self.config_extensions = config_extensions
        self.binary_extensions = binary_extensions

    def should_skip_directory(self, dir_name: str) -> bool:
        """Check if a directory should be skipped.

        Args:
            dir_name: Directory name (not full path).

        Returns:
            True if directory should be skipped.
        """
        return dir_name in self.skip_directories

    def get_category(self, extension: str) -> FileCategory:
        """Determine file category from extension.

        Args:
            extension: File extension including dot (e.g., ".py").

        Returns:
            File category.
        """
        ext_lower = extension.lower()

        if ext_lower in self.code_extensions:
            return FileCategory.CODE
        elif ext_lower in self.doc_extensions:
            return FileCategory.DOCUMENTATION
        elif ext_lower in self.config_extensions:
            return FileCategory.CONFIGURATION
        elif ext_lower in self.binary_extensions:
            return FileCategory.BINARY
        else:
            return FileCategory.UNKNOWN

    def determine_action(
        self,
        size_bytes: int,
        category: FileCategory,
        path_length: int,
    ) -> IndexAction:
        """Determine what action to take for a file.

        Args:
            size_bytes: File size in bytes.
            category: File category.
            path_length: Length of file path.

        Returns:
            Action to take for the file.
        """
        # Skip binary files
        if category == FileCategory.BINARY:
            return IndexAction.SKIP

        # Skip files with paths too long
        if path_length > self.max_path_length:
            logger.debug("Path too long, skipping", path_length=path_length)
            return IndexAction.SKIP

        # Catalog-only for files over threshold
        if size_bytes > self.catalog_threshold:
            logger.debug(
                "File too large for full index",
                size_bytes=size_bytes,
                threshold=self.catalog_threshold,
            )
            return IndexAction.CATALOG_ONLY

        # Full index for recognized types
        if category in (
            FileCategory.CODE,
            FileCategory.DOCUMENTATION,
            FileCategory.CONFIGURATION,
        ):
            return IndexAction.FULL_INDEX

        # Unknown files get catalog-only
        return IndexAction.CATALOG_ONLY

    def analyze_file(
        self,
        file_path: Path,
        relative_path: str,
        size_bytes: int | None = None,
    ) -> FileInfo:
        """Analyze a file and determine its indexing treatment.

        Args:
            file_path: Absolute path to file.
            relative_path: Path relative to repository root.
            size_bytes: File size (will be read if not provided).

        Returns:
            FileInfo with category and action.
        """
        if size_bytes is None:
            try:
                size_bytes = file_path.stat().st_size
            except OSError:
                size_bytes = 0

        extension = file_path.suffix
        category = self.get_category(extension)
        action = self.determine_action(
            size_bytes=size_bytes,
            category=category,
            path_length=len(relative_path),
        )

        return FileInfo(
            path=file_path,
            relative_path=relative_path,
            size_bytes=size_bytes,
            extension=extension,
            category=category,
            action=action,
        )


def is_text_file(file_path: Path, sample_size: int = 8192) -> bool:
    """Check if a file appears to be text (not binary).

    Args:
        file_path: Path to file.
        sample_size: Number of bytes to sample.

    Returns:
        True if file appears to be text.
    """
    try:
        with open(file_path, "rb") as f:
            sample = f.read(sample_size)

        # Empty files are text
        if not sample:
            return True

        # Check for null bytes (common in binary files)
        if b"\x00" in sample:
            return False

        # Try to decode as UTF-8
        try:
            sample.decode("utf-8")
            return True
        except UnicodeDecodeError:
            pass

        # Try Latin-1 as fallback
        try:
            sample.decode("latin-1")
            return True
        except UnicodeDecodeError:
            return False

    except OSError:
        return False


# Default filter instance
_default_filter: FileFilter | None = None


def get_file_filter() -> FileFilter:
    """Get the default file filter instance."""
    global _default_filter
    if _default_filter is None:
        _default_filter = FileFilter()
    return _default_filter
