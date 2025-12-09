"""Chonkie-based chunking and embedding utility."""

from typing import Any

from chonkie import TokenChunker  # type: ignore[attr-defined]

from backend.src.config.constants import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SIZE_TOKENS,
    MAX_CHUNKS_PER_FILE,
)
from backend.src.config.logging import get_logger

logger = get_logger(__name__)


class ChunkResult:
    """Result of chunking a document."""

    def __init__(
        self,
        content: str,
        line_start: int,
        line_end: int,
        token_count: int,
    ) -> None:
        """Initialize chunk result.

        Args:
            content: The chunked text content.
            line_start: Starting line number (1-indexed).
            line_end: Ending line number (1-indexed).
            token_count: Number of tokens in the chunk.
        """
        self.content = content
        self.line_start = line_start
        self.line_end = line_end
        self.token_count = token_count

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with chunk data.
        """
        return {
            "content": self.content,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "token_count": self.token_count,
        }


def _get_chunker() -> TokenChunker:
    """Get configured TokenChunker instance.

    Returns:
        Configured TokenChunker for splitting text.
    """
    return TokenChunker(
        chunk_size=CHUNK_SIZE_TOKENS,
        chunk_overlap=CHUNK_OVERLAP_TOKENS,
    )


def _calculate_line_numbers(
    full_text: str,
    chunk_start_char: int,
    chunk_end_char: int,
) -> tuple[int, int]:
    """Calculate line numbers for a chunk within the full text.

    Args:
        full_text: The complete text content.
        chunk_start_char: Character position where chunk starts.
        chunk_end_char: Character position where chunk ends.

    Returns:
        Tuple of (start_line, end_line) both 1-indexed.
    """
    # Count newlines before chunk start to get starting line
    text_before = full_text[:chunk_start_char]
    start_line = text_before.count("\n") + 1

    # Count newlines within chunk to get ending line
    chunk_text = full_text[chunk_start_char:chunk_end_char]
    end_line = start_line + chunk_text.count("\n")

    return start_line, end_line


def chunk_text(
    content: str,
    max_chunks: int | None = None,
) -> list[ChunkResult]:
    """Chunk text content for indexing.

    Args:
        content: Text content to chunk.
        max_chunks: Maximum number of chunks to return.

    Returns:
        List of ChunkResult objects with content and line numbers.
    """
    if max_chunks is None:
        max_chunks = MAX_CHUNKS_PER_FILE

    if not content or not content.strip():
        return []

    chunker = _get_chunker()

    try:
        chunks = chunker.chunk(content)
    except Exception as e:
        logger.warning(
            "Failed to chunk content, returning single chunk",
            error=str(e),
        )
        # Fallback: return entire content as single chunk
        lines = content.split("\n")
        return [
            ChunkResult(
                content=content,
                line_start=1,
                line_end=len(lines),
                token_count=len(content.split()),  # Rough estimate
            )
        ]

    results: list[ChunkResult] = []
    current_position = 0

    for chunk in chunks[:max_chunks]:
        chunk_text_content = chunk.text

        # Find the chunk's position in the original text
        chunk_start = content.find(chunk_text_content, current_position)
        if chunk_start == -1:
            # If exact match not found, use approximate position
            chunk_start = current_position

        chunk_end = chunk_start + len(chunk_text_content)
        current_position = chunk_start + 1  # Move past for next search

        # Calculate line numbers
        start_line, end_line = _calculate_line_numbers(content, chunk_start, chunk_end)

        results.append(
            ChunkResult(
                content=chunk_text_content,
                line_start=start_line,
                line_end=end_line,
                token_count=chunk.token_count,
            )
        )

    logger.debug(
        "Chunked content",
        chunk_count=len(results),
        total_tokens=sum(c.token_count for c in results),
    )

    return results


def chunk_code_file(
    content: str,
    language: str | None = None,
    max_chunks: int | None = None,
) -> list[ChunkResult]:
    """Chunk code file content with language awareness.

    Currently delegates to chunk_text, but can be extended
    for language-specific chunking strategies.

    Args:
        content: Code file content.
        language: Programming language (e.g., "python", "javascript").
        max_chunks: Maximum number of chunks.

    Returns:
        List of ChunkResult objects.
    """
    # For now, use the same chunking strategy
    # Future: implement language-aware chunking (by function, class, etc.)
    logger.debug("Chunking code file", language=language)
    return chunk_text(content, max_chunks)


def estimate_token_count(text: str) -> int:
    """Estimate token count for text.

    This is a rough estimate based on word count.
    For accurate counts, use the tokenizer directly.

    Args:
        text: Text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    # Rough estimate: ~1.3 tokens per word for code
    words = len(text.split())
    return int(words * 1.3)


class Chunk:
    """A chunk of text with optional embedding."""

    def __init__(
        self,
        text: str,
        token_count: int,
        embedding: list[float] | None = None,
    ) -> None:
        """Initialize chunk.

        Args:
            text: The chunk text content.
            token_count: Number of tokens in the chunk.
            embedding: Optional embedding vector.
        """
        self.text = text
        self.token_count = token_count
        self.embedding = embedding


class ChunkingService:
    """Service for chunking text content."""

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE_TOKENS,
        chunk_overlap: int = CHUNK_OVERLAP_TOKENS,
        max_chunks: int = MAX_CHUNKS_PER_FILE,
    ) -> None:
        """Initialize chunking service.

        Args:
            chunk_size: Target chunk size in tokens.
            chunk_overlap: Overlap between chunks in tokens.
            max_chunks: Maximum number of chunks per document.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_chunks = max_chunks

    def chunk_text(self, content: str) -> list[Chunk]:
        """Chunk text content.

        Args:
            content: Text content to chunk.

        Returns:
            List of Chunk objects.
        """
        results = chunk_text(content, self.max_chunks)
        return [
            Chunk(
                text=result.content,
                token_count=result.token_count,
                embedding=None,
            )
            for result in results
        ]


# Service singleton
_chunking_service: ChunkingService | None = None


def get_chunking_service() -> ChunkingService:
    """Get chunking service singleton.

    Returns:
        ChunkingService instance.
    """
    global _chunking_service
    if _chunking_service is None:
        _chunking_service = ChunkingService()
    return _chunking_service
