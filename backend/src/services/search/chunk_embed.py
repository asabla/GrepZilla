"""Chonkie-based chunking and embedding utility with AST-aware CodeChunker support."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from chonkie import TokenChunker  # type: ignore[attr-defined]

from backend.src.config.constants import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SIZE_TOKENS,
    MAX_CHUNKS_PER_FILE,
)
from backend.src.config.feature_flags import (
    is_code_chunker_enabled,
    should_fallback_on_chunker_error,
)
from backend.src.config.logging import get_logger
from backend.src.config.settings import get_settings

logger = get_logger(__name__)


class ChunkerMode(StrEnum):
    """Available chunker modes."""

    TOKEN = "token"
    CODE_AUTO = "code_auto"
    CODE_LANG_PYTHON = "code_lang_python"
    CODE_LANG_TYPESCRIPT = "code_lang_typescript"
    CODE_LANG_JAVASCRIPT = "code_lang_javascript"
    CODE_LANG_GO = "code_lang_go"
    CODE_LANG_RUST = "code_lang_rust"
    CODE_LANG_JAVA = "code_lang_java"
    CODE_LANG_C = "code_lang_c"
    CODE_LANG_CPP = "code_lang_cpp"
    CODE_LANG_CSHARP = "code_lang_csharp"
    CODE_LANG_RUBY = "code_lang_ruby"
    CODE_LANG_PHP = "code_lang_php"


# Extension to tree-sitter language mapping for CodeChunker
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".cs": "c_sharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".lua": "lua",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".sql": "sql",
    ".r": "r",
    ".R": "r",
}


def get_language_from_extension(extension: str) -> str | None:
    """Get tree-sitter language name from file extension.

    Args:
        extension: File extension including dot (e.g., ".py").

    Returns:
        Language name for CodeChunker or None if not supported.
    """
    return EXTENSION_TO_LANGUAGE.get(extension.lower())


def get_language_from_mode(mode: str) -> str | None:
    """Extract language from chunker mode string.

    Args:
        mode: Chunker mode (e.g., "code_lang_python").

    Returns:
        Language name or None if mode is not language-specific.
    """
    if mode.startswith("code_lang_"):
        lang = mode.replace("code_lang_", "")
        # Handle c_sharp special case
        if lang == "csharp":
            return "c_sharp"
        return lang
    return None


@dataclass
class ChunkResult:
    """Result of chunking a document."""

    content: str
    line_start: int
    line_end: int
    token_count: int
    start_index: int | None = None  # Character offset in original text
    end_index: int | None = None  # Character offset in original text
    chunking_mode: str = "token"  # Which chunker produced this

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
            "start_index": self.start_index,
            "end_index": self.end_index,
            "chunking_mode": self.chunking_mode,
        }


def _get_token_chunker(
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> TokenChunker:
    """Get configured TokenChunker instance.

    Args:
        chunk_size: Target chunk size in tokens (defaults to config).
        chunk_overlap: Overlap between chunks (defaults to config).

    Returns:
        Configured TokenChunker for splitting text.
    """
    settings = get_settings()
    return TokenChunker(
        chunk_size=chunk_size or settings.chunker_size_tokens or CHUNK_SIZE_TOKENS,
        chunk_overlap=chunk_overlap
        or settings.chunker_overlap_tokens
        or CHUNK_OVERLAP_TOKENS,
    )


def _get_code_chunker(
    language: str = "auto",
    chunk_size: int | None = None,
) -> Any:
    """Get configured CodeChunker instance.

    Args:
        language: Language for AST parsing ("auto" for detection).
        chunk_size: Target chunk size in tokens.

    Returns:
        Configured CodeChunker for AST-aware splitting.

    Raises:
        ImportError: If chonkie[code] is not installed.
    """
    try:
        from chonkie.experimental import CodeChunker  # type: ignore[import-untyped]
    except ImportError as e:
        logger.error(
            "CodeChunker not available - install chonkie[code]",
            error=str(e),
        )
        raise ImportError(
            "CodeChunker requires chonkie[code] extra: pip install chonkie[code]"
        ) from e

    settings = get_settings()
    return CodeChunker(
        language=language,
        chunk_size=chunk_size or settings.chunker_size_tokens or CHUNK_SIZE_TOKENS,
        add_split_context=settings.code_chunker_include_context,
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


def _chunk_with_token_chunker(
    content: str,
    max_chunks: int,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[ChunkResult]:
    """Chunk content using TokenChunker.

    Args:
        content: Text content to chunk.
        max_chunks: Maximum number of chunks to return.
        chunk_size: Target chunk size in tokens.
        chunk_overlap: Overlap between chunks.

    Returns:
        List of ChunkResult objects with content and line numbers.
    """
    chunker = _get_token_chunker(chunk_size, chunk_overlap)

    try:
        chunks = chunker.chunk(content)
    except Exception as e:
        logger.warning(
            "TokenChunker failed, returning single chunk",
            error=str(e),
        )
        lines = content.split("\n")
        return [
            ChunkResult(
                content=content,
                line_start=1,
                line_end=len(lines),
                token_count=len(content.split()),
                start_index=0,
                end_index=len(content),
                chunking_mode="token_fallback",
            )
        ]

    results: list[ChunkResult] = []
    current_position = 0

    for chunk in chunks[:max_chunks]:
        chunk_text_content = chunk.text

        # Find the chunk's position in the original text
        chunk_start = content.find(chunk_text_content, current_position)
        if chunk_start == -1:
            chunk_start = current_position

        chunk_end = chunk_start + len(chunk_text_content)
        current_position = chunk_start + 1

        start_line, end_line = _calculate_line_numbers(content, chunk_start, chunk_end)

        results.append(
            ChunkResult(
                content=chunk_text_content,
                line_start=start_line,
                line_end=end_line,
                token_count=chunk.token_count,
                start_index=chunk_start,
                end_index=chunk_end,
                chunking_mode="token",
            )
        )

    return results


def _chunk_with_code_chunker(
    content: str,
    language: str,
    max_chunks: int,
    chunk_size: int | None = None,
) -> list[ChunkResult]:
    """Chunk content using AST-aware CodeChunker.

    Args:
        content: Code content to chunk.
        language: Programming language ("auto" for detection).
        max_chunks: Maximum number of chunks to return.
        chunk_size: Target chunk size in tokens.

    Returns:
        List of ChunkResult objects with content and line numbers.

    Raises:
        Exception: If CodeChunker fails and fallback is disabled.
    """
    chunker = _get_code_chunker(language, chunk_size)

    chunks = chunker.chunk(content)

    results: list[ChunkResult] = []
    for chunk in chunks[:max_chunks]:
        # CodeChunker provides start_index and end_index directly
        chunk_start = getattr(chunk, "start_index", 0)
        chunk_end = getattr(chunk, "end_index", len(chunk.text))

        start_line, end_line = _calculate_line_numbers(content, chunk_start, chunk_end)

        results.append(
            ChunkResult(
                content=chunk.text,
                line_start=start_line,
                line_end=end_line,
                token_count=getattr(chunk, "token_count", len(chunk.text.split())),
                start_index=chunk_start,
                end_index=chunk_end,
                chunking_mode=f"code_{language}",
            )
        )

    return results


def chunk_text(
    content: str,
    max_chunks: int | None = None,
    language: str | None = None,
    file_extension: str | None = None,
) -> list[ChunkResult]:
    """Chunk text content for indexing.

    Uses CodeChunker if enabled and appropriate, otherwise falls back to TokenChunker.

    Args:
        content: Text content to chunk.
        max_chunks: Maximum number of chunks to return.
        language: Programming language hint (e.g., "python").
        file_extension: File extension for language detection (e.g., ".py").

    Returns:
        List of ChunkResult objects with content and line numbers.
    """
    if max_chunks is None:
        max_chunks = MAX_CHUNKS_PER_FILE

    if not content or not content.strip():
        return []

    settings = get_settings()
    chunker_mode = settings.chunker_mode
    code_chunker_enabled = is_code_chunker_enabled()

    # Determine if we should use CodeChunker
    use_code_chunker = False
    detected_language = language

    if code_chunker_enabled and chunker_mode != ChunkerMode.TOKEN:
        # Check if mode specifies a language
        mode_language = get_language_from_mode(chunker_mode)
        if mode_language:
            detected_language = mode_language
            use_code_chunker = True
        elif chunker_mode == ChunkerMode.CODE_AUTO:
            # Auto-detect from extension or use "auto"
            if file_extension:
                detected_language = get_language_from_extension(file_extension)
            if detected_language:
                use_code_chunker = True
            else:
                # Fall back to CodeChunker with auto-detection
                detected_language = "auto"
                use_code_chunker = True

    if use_code_chunker and detected_language:
        try:
            logger.debug(
                "Using CodeChunker",
                language=detected_language,
                mode=chunker_mode,
            )
            results = _chunk_with_code_chunker(
                content,
                detected_language,
                max_chunks,
                settings.chunker_size_tokens,
            )
            logger.debug(
                "CodeChunker completed",
                chunk_count=len(results),
                total_tokens=sum(c.token_count for c in results),
            )
            return results
        except Exception as e:
            logger.warning(
                "CodeChunker failed",
                error=str(e),
                language=detected_language,
            )
            if not should_fallback_on_chunker_error():
                raise

            logger.info("Falling back to TokenChunker")

    # Use TokenChunker (default or fallback)
    results = _chunk_with_token_chunker(
        content,
        max_chunks,
        settings.chunker_size_tokens,
        settings.chunker_overlap_tokens,
    )

    logger.debug(
        "Chunked content",
        chunk_count=len(results),
        total_tokens=sum(c.token_count for c in results),
        mode="token",
    )

    return results


def chunk_code_file(
    content: str,
    language: str | None = None,
    file_extension: str | None = None,
    max_chunks: int | None = None,
) -> list[ChunkResult]:
    """Chunk code file content with language awareness.

    Uses AST-aware CodeChunker when enabled and language is supported.

    Args:
        content: Code file content.
        language: Programming language (e.g., "python", "javascript").
        file_extension: File extension for language detection (e.g., ".py").
        max_chunks: Maximum number of chunks.

    Returns:
        List of ChunkResult objects.
    """
    # Derive language from extension if not provided
    if not language and file_extension:
        language = get_language_from_extension(file_extension)

    logger.debug(
        "Chunking code file",
        language=language,
        extension=file_extension,
    )

    return chunk_text(
        content,
        max_chunks=max_chunks,
        language=language,
        file_extension=file_extension,
    )


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
        line_start: int = 1,
        line_end: int = 1,
        start_index: int | None = None,
        end_index: int | None = None,
        chunking_mode: str = "token",
    ) -> None:
        """Initialize chunk.

        Args:
            text: The chunk text content.
            token_count: Number of tokens in the chunk.
            embedding: Optional embedding vector.
            line_start: Starting line number (1-indexed).
            line_end: Ending line number (1-indexed).
            start_index: Character offset start in original text.
            end_index: Character offset end in original text.
            chunking_mode: Which chunker produced this chunk.
        """
        self.text = text
        self.token_count = token_count
        self.embedding = embedding
        self.line_start = line_start
        self.line_end = line_end
        self.start_index = start_index
        self.end_index = end_index
        self.chunking_mode = chunking_mode


class ChunkingService:
    """Service for chunking text content with configurable chunker."""

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

    def chunk_text(
        self,
        content: str,
        language: str | None = None,
        file_extension: str | None = None,
    ) -> list[Chunk]:
        """Chunk text content.

        Args:
            content: Text content to chunk.
            language: Programming language hint.
            file_extension: File extension for language detection.

        Returns:
            List of Chunk objects.
        """
        results = chunk_text(
            content,
            max_chunks=self.max_chunks,
            language=language,
            file_extension=file_extension,
        )
        return [
            Chunk(
                text=result.content,
                token_count=result.token_count,
                embedding=None,
                line_start=result.line_start,
                line_end=result.line_end,
                start_index=result.start_index,
                end_index=result.end_index,
                chunking_mode=result.chunking_mode,
            )
            for result in results
        ]

    def chunk_code(
        self,
        content: str,
        language: str | None = None,
        file_extension: str | None = None,
    ) -> list[Chunk]:
        """Chunk code content with language awareness.

        Args:
            content: Code content to chunk.
            language: Programming language.
            file_extension: File extension.

        Returns:
            List of Chunk objects.
        """
        results = chunk_code_file(
            content,
            language=language,
            file_extension=file_extension,
            max_chunks=self.max_chunks,
        )
        return [
            Chunk(
                text=result.content,
                token_count=result.token_count,
                embedding=None,
                line_start=result.line_start,
                line_end=result.line_end,
                start_index=result.start_index,
                end_index=result.end_index,
                chunking_mode=result.chunking_mode,
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
        settings = get_settings()
        _chunking_service = ChunkingService(
            chunk_size=settings.chunker_size_tokens or CHUNK_SIZE_TOKENS,
            chunk_overlap=settings.chunker_overlap_tokens or CHUNK_OVERLAP_TOKENS,
            max_chunks=MAX_CHUNKS_PER_FILE,
        )
    return _chunking_service


def reset_chunking_service() -> None:
    """Reset chunking service singleton (useful for testing)."""
    global _chunking_service
    _chunking_service = None
