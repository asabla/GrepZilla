"""Embedding and chunking for ingestion pipeline."""

import asyncio
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
from backend.src.services.ai.embeddings import EmbeddingClient, get_embedding_client
from backend.src.services.ingestion.file_filters import FileInfo
from backend.src.services.search.chunk_embed import (
    ChunkingService,
    get_chunking_service,
    get_language_from_extension,
)

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
    start_index: int | None = None  # Character offset in original file
    end_index: int | None = None  # Character offset in original file
    chunking_mode: str = "token"  # Which chunker produced this
    language: str | None = None  # Detected/specified programming language


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
        embedding_client: EmbeddingClient | None = None,
        chunk_size: int = CHUNK_SIZE_TOKENS,
        chunk_overlap: int = CHUNK_OVERLAP_TOKENS,
        max_chunks: int = MAX_CHUNKS_PER_FILE,
    ):
        """Initialize embedding service.

        Args:
            chunking_service: Chunking service instance.
            embedding_client: Embedding client instance.
            chunk_size: Target chunk size in tokens.
            chunk_overlap: Overlap between chunks.
            max_chunks: Maximum chunks per file.
        """
        self.chunking_service = chunking_service or get_chunking_service()
        self.embedding_client = embedding_client or get_embedding_client()
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

            # Derive language from file extension for code-aware chunking
            file_extension = file_info.extension
            language = (
                get_language_from_extension(file_extension) if file_extension else None
            )

            # Chunk the content with language awareness
            chunks = self.chunking_service.chunk_text(
                content,
                language=language,
                file_extension=file_extension,
            )

            # Limit chunks per file
            if len(chunks) > self.max_chunks:
                logger.warning(
                    "Truncating chunks",
                    file_path=file_info.relative_path,
                    original_count=len(chunks),
                    max_count=self.max_chunks,
                )
                chunks = chunks[: self.max_chunks]

            # Generate embeddings for all chunks in batch
            chunk_texts = [chunk.text for chunk in chunks]
            embeddings: list[list[float]] = []
            if chunk_texts and self.embedding_client.enabled:
                try:
                    embeddings = asyncio.run(
                        self.embedding_client.embed_batch(chunk_texts)
                    )
                    logger.debug(
                        "Generated embeddings for file",
                        file_path=file_info.relative_path,
                        chunk_count=len(chunks),
                        embedding_count=len(embeddings),
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to generate embeddings, continuing without",
                        file_path=file_info.relative_path,
                        error=str(e),
                    )
                    embeddings = []

            # Process each chunk - use line numbers from chunk if available
            for idx, chunk in enumerate(chunks):
                # Use line numbers computed by chunker (more accurate for CodeChunker)
                line_start = chunk.line_start
                line_end = chunk.line_end

                # Generate chunk ID
                chunk_id = self._generate_chunk_id(
                    repository_id=repository_id,
                    branch_id=branch_id,
                    file_path=file_info.relative_path,
                    chunk_index=idx,
                )

                # Calculate content hash
                content_hash = hashlib.sha256(chunk.text.encode()).hexdigest()[:16]

                # Get embedding for this chunk (if available)
                chunk_embedding = embeddings[idx] if idx < len(embeddings) else None

                embedded_chunk = EmbeddedChunk(
                    id=chunk_id,
                    content=chunk.text,
                    embedding=chunk_embedding,
                    file_path=file_info.relative_path,
                    line_start=line_start,
                    line_end=line_end,
                    token_count=chunk.token_count,
                    chunk_index=idx,
                    content_hash=content_hash,
                    start_index=chunk.start_index,
                    end_index=chunk.end_index,
                    chunking_mode=chunk.chunking_mode,
                    language=language,
                )

                result.chunks.append(embedded_chunk)
                result.total_tokens += chunk.token_count

            logger.debug(
                "File processed",
                file_path=file_info.relative_path,
                chunks=len(result.chunks),
                total_tokens=result.total_tokens,
                embeddings_generated=len(embeddings) > 0,
                language=language,
                chunking_mode=chunks[0].chunking_mode if chunks else "none",
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
                with open(file_path, encoding=encoding) as f:
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
