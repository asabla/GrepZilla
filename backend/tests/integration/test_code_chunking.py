"""Integration tests for code chunking in ingestion pipeline."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.src.services.ingestion.embed import EmbedService, EmbeddingResult
from backend.src.services.ingestion.file_filters import (
    FileCategory,
    FileFilter,
    FileInfo,
    IndexAction,
)
from backend.src.services.search.chunk_embed import (
    ChunkingService,
    get_chunking_service,
    reset_chunking_service,
)


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset chunking service singleton before each test."""
    reset_chunking_service()


@pytest.fixture
def sample_python_code() -> str:
    """Sample Python code for chunking tests."""
    return '''"""Module docstring."""

import os
from typing import List

CONSTANT = "value"


def process_files(directory: str) -> List[str]:
    """Process all files in a directory.
    
    Args:
        directory: Path to the directory.
        
    Returns:
        List of processed file names.
    """
    files = []
    for filename in os.listdir(directory):
        if filename.endswith('.py'):
            files.append(filename)
    return files


class FileProcessor:
    """Process files with various methods."""
    
    def __init__(self, base_dir: str) -> None:
        """Initialize processor."""
        self.base_dir = base_dir
        self.processed_count = 0
    
    def process(self, filename: str) -> bool:
        """Process a single file.
        
        Args:
            filename: Name of the file to process.
            
        Returns:
            True if processing succeeded.
        """
        # Processing logic here
        self.processed_count += 1
        return True
    
    def get_stats(self) -> dict:
        """Get processing statistics."""
        return {"processed": self.processed_count}


if __name__ == "__main__":
    processor = FileProcessor("/tmp")
    processor.process("test.py")
'''


@pytest.fixture
def sample_javascript_code() -> str:
    """Sample JavaScript code for chunking tests."""
    return """/**
 * Module for file processing utilities.
 */

const fs = require('fs');
const path = require('path');

/**
 * Process files in a directory.
 * @param {string} directory - Path to the directory.
 * @returns {string[]} List of processed file names.
 */
function processFiles(directory) {
    const files = [];
    const items = fs.readdirSync(directory);
    
    for (const item of items) {
        if (item.endsWith('.js')) {
            files.push(item);
        }
    }
    
    return files;
}

/**
 * File processor class.
 */
class FileProcessor {
    constructor(baseDir) {
        this.baseDir = baseDir;
        this.processedCount = 0;
    }
    
    process(filename) {
        // Processing logic here
        this.processedCount++;
        return true;
    }
    
    getStats() {
        return { processed: this.processedCount };
    }
}

module.exports = { processFiles, FileProcessor };
"""


class TestChunkingServiceIntegration:
    """Integration tests for ChunkingService."""

    def test_chunking_service_processes_python_code(
        self,
        sample_python_code: str,
    ) -> None:
        """Should chunk Python code correctly."""
        service = get_chunking_service()
        chunks = service.chunk_text(sample_python_code, language="python")

        assert len(chunks) >= 1
        # Verify chunk contains code content
        combined_content = "".join(c.text for c in chunks)
        assert "process_files" in combined_content
        assert "FileProcessor" in combined_content

        # Verify line numbers are reasonable
        for chunk in chunks:
            assert chunk.line_start >= 1
            assert chunk.line_end >= chunk.line_start

    def test_chunking_service_processes_javascript_code(
        self,
        sample_javascript_code: str,
    ) -> None:
        """Should chunk JavaScript code correctly."""
        service = get_chunking_service()
        chunks = service.chunk_text(
            sample_javascript_code,
            language="javascript",
            file_extension=".js",
        )

        assert len(chunks) >= 1
        combined_content = "".join(c.text for c in chunks)
        assert "processFiles" in combined_content or "FileProcessor" in combined_content

    def test_chunking_service_with_file_extension(
        self,
        sample_python_code: str,
    ) -> None:
        """Should derive language from file extension."""
        service = get_chunking_service()
        chunks = service.chunk_text(
            sample_python_code,
            file_extension=".py",
        )

        assert len(chunks) >= 1
        # Each chunk should have metadata
        for chunk in chunks:
            assert chunk.token_count > 0
            assert chunk.chunking_mode is not None


class TestEmbedServiceIntegration:
    """Integration tests for EmbedService with code chunking."""

    def test_embed_service_processes_python_file(
        self,
        sample_python_code: str,
    ) -> None:
        """Should process a Python file with language-aware chunking."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(sample_python_code)
            temp_path = Path(f.name)

        try:
            # Create file info
            file_info = FileInfo(
                path=temp_path,
                relative_path="test_module.py",
                extension=".py",
                size_bytes=len(sample_python_code),
                category=FileCategory.CODE,
                action=IndexAction.FULL_INDEX,
            )

            # Create embed service with disabled embeddings
            embed_client_mock = MagicMock()
            embed_client_mock.enabled = False

            service = EmbedService(
                embedding_client=embed_client_mock,
            )

            result = service.process_file(
                file_info=file_info,
                repository_id="test-repo-id",
                branch_id="test-branch-id",
            )

            # Verify result
            assert result.error is None
            assert len(result.chunks) >= 1
            assert result.total_tokens > 0

            # Verify chunk metadata
            for chunk in result.chunks:
                assert chunk.id is not None
                assert chunk.content is not None
                assert chunk.file_path == "test_module.py"
                assert chunk.line_start >= 1
                assert chunk.line_end >= chunk.line_start
                assert chunk.content_hash is not None
                # New metadata fields
                assert chunk.chunking_mode is not None
                assert chunk.language == "python"

        finally:
            temp_path.unlink()

    def test_embed_service_derives_language_from_extension(
        self,
        sample_javascript_code: str,
    ) -> None:
        """Should derive language from file extension."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(sample_javascript_code)
            temp_path = Path(f.name)

        try:
            file_info = FileInfo(
                path=temp_path,
                relative_path="utils.js",
                extension=".js",
                size_bytes=len(sample_javascript_code),
                category=FileCategory.CODE,
                action=IndexAction.FULL_INDEX,
            )

            embed_client_mock = MagicMock()
            embed_client_mock.enabled = False

            service = EmbedService(embedding_client=embed_client_mock)

            result = service.process_file(
                file_info=file_info,
                repository_id="test-repo-id",
                branch_id="test-branch-id",
            )

            assert result.error is None
            assert len(result.chunks) >= 1
            # Verify language was detected
            for chunk in result.chunks:
                assert chunk.language == "javascript"

        finally:
            temp_path.unlink()

    def test_embed_service_handles_unknown_extension(self) -> None:
        """Should handle files with unknown extensions."""
        content = "some random text content"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xyz", delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)

        try:
            file_info = FileInfo(
                path=temp_path,
                relative_path="unknown.xyz",
                extension=".xyz",
                size_bytes=len(content),
                category=FileCategory.UNKNOWN,
                action=IndexAction.FULL_INDEX,
            )

            embed_client_mock = MagicMock()
            embed_client_mock.enabled = False

            service = EmbedService(embedding_client=embed_client_mock)

            result = service.process_file(
                file_info=file_info,
                repository_id="test-repo-id",
                branch_id="test-branch-id",
            )

            assert result.error is None
            assert len(result.chunks) >= 1
            # Should use token chunker for unknown extension
            for chunk in result.chunks:
                assert chunk.language is None
                assert chunk.chunking_mode == "token"

        finally:
            temp_path.unlink()


class TestFileFilterIntegration:
    """Integration tests for file filtering with chunking."""

    def test_file_filter_categorizes_code_files(self) -> None:
        """Should correctly categorize code file extensions."""
        file_filter = FileFilter()

        code_extensions = [".py", ".js", ".ts", ".go", ".rs", ".java"]
        for ext in code_extensions:
            category = file_filter.get_category(ext)
            assert category.value == "code", f"Expected 'code' for {ext}"

    def test_file_filter_categorizes_documentation(self) -> None:
        """Should correctly categorize documentation files."""
        file_filter = FileFilter()

        doc_extensions = [".md", ".rst", ".txt"]
        for ext in doc_extensions:
            category = file_filter.get_category(ext)
            assert category.value == "documentation", (
                f"Expected 'documentation' for {ext}"
            )


class TestChunkMetadata:
    """Tests for chunk metadata propagation."""

    def test_chunk_metadata_includes_character_offsets(
        self,
        sample_python_code: str,
    ) -> None:
        """Should include character offset metadata in chunks."""
        service = get_chunking_service()
        chunks = service.chunk_text(sample_python_code)

        # At least some chunks should have offsets
        # (depends on chunker mode - token chunker includes them)
        for chunk in chunks:
            if chunk.start_index is not None:
                assert chunk.end_index is not None
                assert chunk.end_index >= chunk.start_index

    def test_chunk_metadata_includes_chunking_mode(
        self,
        sample_python_code: str,
    ) -> None:
        """Should include chunking mode in metadata."""
        service = get_chunking_service()
        chunks = service.chunk_text(sample_python_code)

        for chunk in chunks:
            assert chunk.chunking_mode is not None
            assert isinstance(chunk.chunking_mode, str)


class TestCodeChunkerWithFeatureFlag:
    """Tests for CodeChunker with feature flag control."""

    @patch("backend.src.services.search.chunk_embed.is_code_chunker_enabled")
    @patch("backend.src.services.search.chunk_embed.get_settings")
    def test_code_chunker_disabled_by_default(
        self,
        mock_settings: MagicMock,
        mock_enabled: MagicMock,
        sample_python_code: str,
    ) -> None:
        """Should use token chunker when feature flag is disabled."""
        mock_enabled.return_value = False

        settings_mock = MagicMock()
        settings_mock.chunker_mode = "token"
        settings_mock.chunker_size_tokens = 512
        settings_mock.chunker_overlap_tokens = 64
        mock_settings.return_value = settings_mock

        service = ChunkingService()
        chunks = service.chunk_text(sample_python_code, language="python")

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.chunking_mode == "token"

    @patch("backend.src.services.search.chunk_embed.is_code_chunker_enabled")
    @patch("backend.src.services.search.chunk_embed.should_fallback_on_chunker_error")
    @patch("backend.src.services.search.chunk_embed.get_settings")
    def test_code_chunker_falls_back_gracefully(
        self,
        mock_settings: MagicMock,
        mock_fallback: MagicMock,
        mock_enabled: MagicMock,
        sample_python_code: str,
    ) -> None:
        """Should fall back to token chunker if CodeChunker unavailable."""
        mock_enabled.return_value = True
        mock_fallback.return_value = True

        settings_mock = MagicMock()
        settings_mock.chunker_mode = "code_auto"
        settings_mock.chunker_size_tokens = 512
        settings_mock.chunker_overlap_tokens = 64
        settings_mock.code_chunker_include_context = True
        mock_settings.return_value = settings_mock

        # Force CodeChunker import to fail
        with patch(
            "backend.src.services.search.chunk_embed._get_code_chunker",
            side_effect=ImportError("Not installed"),
        ):
            service = ChunkingService()
            chunks = service.chunk_text(sample_python_code, language="python")

            # Should succeed with fallback
            assert len(chunks) >= 1
            for chunk in chunks:
                assert "token" in chunk.chunking_mode
