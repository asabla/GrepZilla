"""Embedding and chunking for ingestion pipeline."""

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from backend.src.config.constants import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SIZE_TOKENS,
    MAX_CHUNKS_PER_FILE,
)
from backend.src.config.logging import get_logger
from backend.src.services.ingestion.file_filters import FileInfo
from backend.src.services.search.chunk_embed import ChunkingService, get_chunking_service

logger = get_logger(__name__)


@dataclass
class EmbeddedChunk:
    """A chunk of text with embedding and metadata."""

    id: str
    content: str
    embedding: list[float] | None
    file_path: str
    line_start: int
    line_end: int
    token_count: int
    chunk_index: int
    content_hash: str


@dataclass
class EmbeddingResult:
    """Result of embedding a file."""

    file_path: str
    chunks: list[EmbeddedChunk] = field(default_factory=list)
    total_tokens: int = 0
    error: str | None = None


class EmbedService:
    """Service for chunking and embedding file content."""

    def __init__(
        self,
        chunking_service: ChunkingService | None = None,
        chunk_size: int = CHUNK_SIZE_TOKENS,
        chunk_overlap: int = CHUNK_OVERLAP_TOKENS,
        max_chunks: int = MAX_CHUNKS_PER_FILE,
    ):
        """Initialize embedding service.

        Args:
            chunking_service: Chunking service instance.
            chunk_size: Target chunk size in tokens.
            chunk_overlap: Overlap between chunks.
            max_chunks: Maximum chunks per file.
        """
        self.chunking_service = chunking_service or get_chunking_service()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_chunks = max_chunks

    def process_file(
        self,
        file_info: FileInfo,
        repository_id: str,
        branch_id: str,
    ) -> EmbeddingResult:
        """Process a file into chunks with embeddings.

        Args:
            file_info: File information from discovery.
            repository_id: Repository UUID.
            branch_id: Branch UUID.

        Returns:
            EmbeddingResult with chunks.
        """
        result = EmbeddingResult(file_path=file_info.relative_path)

        try:
            # Read file content
            content = self._read_file(file_info.path)
            if content is None:
                result.error = "Failed to read file"
                return result

            # Split into lines for line number tracking
            lines = content.splitlines(keepends=True)

            # Chunk the content
            chunks = self.chunking_service.chunk_text(content)

            # Limit chunks per file
            if len(chunks) > self.max_chunks:
                logger.warning(
                    "Truncating chunks",
                    file_path=file_info.relative_path,
                    original_count=len(chunks),
                    max_count=self.max_chunks,
                )
                chunks = chunks[: self.max_chunks]

            # Process each chunk
            current_line = 1
            for idx, chunk in enumerate(chunks):
                # Calculate line numbers
                line_start, line_end = self._find_line_range(
                    lines, chunk.text, current_line
                )
                current_line = line_start

                # Generate chunk ID
                chunk_id = self._generate_chunk_id(
                    repository_id=repository_id,
                    branch_id=branch_id,
                    file_path=file_info.relative_path,
                    chunk_index=idx,
                )

                # Calculate content hash
                content_hash = hashlib.sha256(chunk.text.encode()).hexdigest()[:16]

                embedded_chunk = EmbeddedChunk(
                    id=chunk_id,
                    content=chunk.text,
                    embedding=chunk.embedding,
                    file_path=file_info.relative_path,
                    line_start=line_start,
                    line_end=line_end,
                    token_count=chunk.token_count,
                    chunk_index=idx,
                    content_hash=content_hash,
                )

                result.chunks.append(embedded_chunk)
                result.total_tokens += chunk.token_count

            logger.debug(
                "File processed",
                file_path=file_info.relative_path,
                chunks=len(result.chunks),
                total_tokens=result.total_tokens,
            )

        except Exception as e:
            result.error = str(e)
            logger.error(
                "Error processing file",
                file_path=file_info.relative_path,
                error=str(e),
            )

        return result

    def _read_file(self, file_path: Path) -> str | None:
        """Read file content with encoding detection.

        Args:
            file_path: Path to file.

        Returns:
            File content or None if unreadable.
        """
        encodings = ["utf-8", "latin-1", "cp1252"]

        for encoding in encodings:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
            except OSError as e:
                logger.warning(
                    "OS error reading file",
                    file_path=str(file_path),
                    error=str(e),
                )
                return None

        logger.warning(
            "Could not decode file with any encoding",
            file_path=str(file_path),
        )
        return None

    def _find_line_range(
        self,
        lines: list[str],
        chunk_text: str,
        start_from: int,
    ) -> tuple[int, int]:
        """Find the line range for a chunk of text.

        Args:
            lines: List of file lines.
            chunk_text: The chunk text to find.
            start_from: Line number to start searching from.

        Returns:
            Tuple of (start_line, end_line) using 1-based indexing.
        """
        # Simple approach: count newlines in chunk
        chunk_lines = chunk_text.count("\n") + 1
        return start_from, start_from + chunk_lines - 1

    def _generate_chunk_id(
        self,
        repository_id: str,
        branch_id: str,
        file_path: str,
        chunk_index: int,
    ) -> str:
        """Generate a deterministic chunk ID.

        Args:
            repository_id: Repository UUID.
            branch_id: Branch UUID.
            file_path: Relative file path.
            chunk_index: Chunk index within file.

        Returns:
            Chunk ID string.
        """
        # Create deterministic ID based on content location
        content = f"{repository_id}:{branch_id}:{file_path}:{chunk_index}"
        hash_bytes = hashlib.sha256(content.encode()).digest()[:16]
        return str(uuid.UUID(bytes=hash_bytes))


# Service singleton
_embed_service: EmbedService | None = None


def get_embed_service() -> EmbedService:
    """Get embedding service singleton."""
    global _embed_service
    if _embed_service is None:
        _embed_service = EmbedService()
    return _embed_service
