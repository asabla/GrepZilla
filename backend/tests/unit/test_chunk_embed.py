"""Unit tests for chunk_embed module with CodeChunker support."""

from unittest.mock import MagicMock, patch

import pytest

from backend.src.services.search.chunk_embed import (
    EXTENSION_TO_LANGUAGE,
    ChunkResult,
    ChunkerMode,
    ChunkingService,
    _calculate_line_numbers,
    _chunk_with_token_chunker,
    chunk_code_file,
    chunk_text,
    get_language_from_extension,
    get_language_from_mode,
    reset_chunking_service,
)


class TestLanguageMapping:
    """Tests for language extension mapping utilities."""

    def test_get_language_from_extension_python(self) -> None:
        """Should return 'python' for .py extension."""
        assert get_language_from_extension(".py") == "python"
        assert get_language_from_extension(".pyw") == "python"
        assert get_language_from_extension(".pyi") == "python"

    def test_get_language_from_extension_javascript(self) -> None:
        """Should return 'javascript' for JS extensions."""
        assert get_language_from_extension(".js") == "javascript"
        assert get_language_from_extension(".jsx") == "javascript"
        assert get_language_from_extension(".mjs") == "javascript"

    def test_get_language_from_extension_typescript(self) -> None:
        """Should return 'typescript' for TS extensions."""
        assert get_language_from_extension(".ts") == "typescript"
        assert get_language_from_extension(".tsx") == "typescript"

    def test_get_language_from_extension_case_insensitive(self) -> None:
        """Should be case-insensitive for extensions."""
        assert get_language_from_extension(".PY") == "python"
        assert get_language_from_extension(".Py") == "python"

    def test_get_language_from_extension_unknown(self) -> None:
        """Should return None for unknown extensions."""
        assert get_language_from_extension(".xyz") is None
        assert get_language_from_extension(".unknown") is None
        assert get_language_from_extension("") is None

    def test_get_language_from_mode_explicit_language(self) -> None:
        """Should extract language from mode string."""
        assert get_language_from_mode("code_lang_python") == "python"
        assert get_language_from_mode("code_lang_typescript") == "typescript"
        assert get_language_from_mode("code_lang_javascript") == "javascript"

    def test_get_language_from_mode_csharp_special_case(self) -> None:
        """Should handle c_sharp special case."""
        assert get_language_from_mode("code_lang_csharp") == "c_sharp"

    def test_get_language_from_mode_non_language_mode(self) -> None:
        """Should return None for non-language modes."""
        assert get_language_from_mode("token") is None
        assert get_language_from_mode("code_auto") is None

    def test_extension_to_language_coverage(self) -> None:
        """Should have mappings for common code file extensions."""
        common_extensions = [
            ".py",
            ".js",
            ".ts",
            ".go",
            ".rs",
            ".java",
            ".c",
            ".cpp",
            ".cs",
            ".rb",
            ".php",
        ]
        for ext in common_extensions:
            assert ext in EXTENSION_TO_LANGUAGE, f"Missing mapping for {ext}"


class TestLineNumberCalculation:
    """Tests for line number calculation from character offsets."""

    def test_calculate_line_numbers_single_line(self) -> None:
        """Should handle single-line content."""
        content = "hello world"
        start_line, end_line = _calculate_line_numbers(content, 0, len(content))
        assert start_line == 1
        assert end_line == 1

    def test_calculate_line_numbers_multiline(self) -> None:
        """Should correctly count lines in multiline content."""
        content = "line1\nline2\nline3\nline4"
        # First line only
        start, end = _calculate_line_numbers(content, 0, 5)  # "line1"
        assert start == 1
        assert end == 1

        # Lines 2-3
        start, end = _calculate_line_numbers(content, 6, 17)  # "line2\nline3"
        assert start == 2
        assert end == 3

    def test_calculate_line_numbers_chunk_in_middle(self) -> None:
        """Should handle chunks starting in the middle of the file."""
        content = "first\nsecond\nthird\nfourth"
        # "third" starts at position 13
        start, end = _calculate_line_numbers(content, 13, 18)
        assert start == 3
        assert end == 3

    def test_calculate_line_numbers_empty_chunk(self) -> None:
        """Should handle empty chunks."""
        content = "line1\nline2"
        start, end = _calculate_line_numbers(content, 0, 0)
        assert start == 1
        assert end == 1


class TestChunkResult:
    """Tests for ChunkResult dataclass."""

    def test_chunk_result_to_dict(self) -> None:
        """Should convert to dictionary with all fields."""
        result = ChunkResult(
            content="test content",
            line_start=1,
            line_end=5,
            token_count=10,
            start_index=0,
            end_index=12,
            chunking_mode="code_python",
        )
        d = result.to_dict()

        assert d["content"] == "test content"
        assert d["line_start"] == 1
        assert d["line_end"] == 5
        assert d["token_count"] == 10
        assert d["start_index"] == 0
        assert d["end_index"] == 12
        assert d["chunking_mode"] == "code_python"

    def test_chunk_result_defaults(self) -> None:
        """Should have correct default values."""
        result = ChunkResult(
            content="test",
            line_start=1,
            line_end=1,
            token_count=1,
        )
        assert result.start_index is None
        assert result.end_index is None
        assert result.chunking_mode == "token"


class TestTokenChunker:
    """Tests for token-based chunking."""

    def test_chunk_empty_content(self) -> None:
        """Should return empty list for empty content."""
        result = chunk_text("")
        assert result == []

    def test_chunk_whitespace_only(self) -> None:
        """Should return empty list for whitespace-only content."""
        result = chunk_text("   \n\t\n   ")
        assert result == []

    def test_chunk_small_content(self) -> None:
        """Should return single chunk for small content."""
        content = "def hello():\n    print('Hello, World!')"
        result = chunk_text(content)

        assert len(result) >= 1
        assert result[0].content == content or content in result[0].content
        assert result[0].line_start == 1
        assert result[0].chunking_mode == "token"

    def test_chunk_max_chunks_limit(self) -> None:
        """Should respect max_chunks limit."""
        # Create content that would produce many chunks
        content = "x\n" * 5000

        result = chunk_text(content, max_chunks=5)

        assert len(result) <= 5

    def test_chunk_text_preserves_line_numbers(self) -> None:
        """Should preserve accurate line numbers."""
        content = "line1\nline2\nline3\nline4\nline5"
        result = chunk_text(content)

        assert len(result) >= 1
        assert result[0].line_start >= 1


class TestChunkingServiceClass:
    """Tests for ChunkingService class."""

    def setup_method(self) -> None:
        """Reset chunking service singleton before each test."""
        reset_chunking_service()

    def test_chunking_service_default_config(self) -> None:
        """Should initialize with default configuration."""
        service = ChunkingService()
        assert service.chunk_size > 0
        assert service.chunk_overlap >= 0
        assert service.max_chunks > 0

    def test_chunking_service_custom_config(self) -> None:
        """Should accept custom configuration."""
        service = ChunkingService(
            chunk_size=256,
            chunk_overlap=32,
            max_chunks=50,
        )
        assert service.chunk_size == 256
        assert service.chunk_overlap == 32
        assert service.max_chunks == 50

    def test_chunking_service_chunk_text(self) -> None:
        """Should chunk text content."""
        service = ChunkingService()
        content = "def example():\n    return True"

        chunks = service.chunk_text(content)

        assert len(chunks) >= 1
        assert chunks[0].text == content or content in chunks[0].text


class TestChunkCodeFile:
    """Tests for code file chunking function."""

    def test_chunk_code_file_with_language(self) -> None:
        """Should accept language parameter."""
        content = "def hello():\n    pass"
        result = chunk_code_file(content, language="python")

        assert len(result) >= 1
        assert result[0].content == content or content in result[0].content

    def test_chunk_code_file_with_extension(self) -> None:
        """Should derive language from file extension."""
        content = "function hello() {}"
        result = chunk_code_file(content, file_extension=".js")

        assert len(result) >= 1

    def test_chunk_code_file_language_priority(self) -> None:
        """Should use provided language over extension."""
        content = "def hello():\n    pass"
        # Provide conflicting language and extension
        result = chunk_code_file(
            content,
            language="python",
            file_extension=".js",
        )

        assert len(result) >= 1


class TestCodeChunkerIntegration:
    """Tests for CodeChunker integration (requires chonkie[code])."""

    def setup_method(self) -> None:
        """Reset chunking service singleton before each test."""
        reset_chunking_service()

    @patch("backend.src.services.search.chunk_embed.is_code_chunker_enabled")
    @patch("backend.src.services.search.chunk_embed.should_fallback_on_chunker_error")
    def test_code_chunker_disabled_uses_token_chunker(
        self,
        mock_fallback: MagicMock,
        mock_enabled: MagicMock,
    ) -> None:
        """Should use TokenChunker when CodeChunker is disabled."""
        mock_enabled.return_value = False
        mock_fallback.return_value = True

        content = "def test():\n    pass"
        result = chunk_text(content, language="python")

        assert len(result) >= 1
        assert result[0].chunking_mode == "token"

    @patch("backend.src.services.search.chunk_embed.is_code_chunker_enabled")
    @patch("backend.src.services.search.chunk_embed.should_fallback_on_chunker_error")
    @patch("backend.src.services.search.chunk_embed.get_settings")
    def test_code_chunker_fallback_on_error(
        self,
        mock_settings: MagicMock,
        mock_fallback: MagicMock,
        mock_enabled: MagicMock,
    ) -> None:
        """Should fall back to TokenChunker on CodeChunker error."""
        mock_enabled.return_value = True
        mock_fallback.return_value = True

        # Mock settings to enable code_auto mode
        settings_mock = MagicMock()
        settings_mock.chunker_mode = "code_auto"
        settings_mock.chunker_size_tokens = 512
        settings_mock.chunker_overlap_tokens = 64
        settings_mock.code_chunker_include_context = True
        mock_settings.return_value = settings_mock

        # Mock CodeChunker to raise an error
        with patch(
            "backend.src.services.search.chunk_embed._get_code_chunker",
            side_effect=ImportError("chonkie[code] not installed"),
        ):
            content = "def test():\n    pass"
            result = chunk_text(content, language="python")

            # Should fall back to token chunker
            assert len(result) >= 1
            assert "token" in result[0].chunking_mode

    @patch("backend.src.services.search.chunk_embed.is_code_chunker_enabled")
    @patch("backend.src.services.search.chunk_embed.should_fallback_on_chunker_error")
    @patch("backend.src.services.search.chunk_embed.get_settings")
    def test_code_chunker_no_fallback_raises(
        self,
        mock_settings: MagicMock,
        mock_fallback: MagicMock,
        mock_enabled: MagicMock,
    ) -> None:
        """Should raise error when fallback is disabled."""
        mock_enabled.return_value = True
        mock_fallback.return_value = False  # Disable fallback

        settings_mock = MagicMock()
        settings_mock.chunker_mode = "code_auto"
        settings_mock.chunker_size_tokens = 512
        settings_mock.code_chunker_include_context = True
        mock_settings.return_value = settings_mock

        with patch(
            "backend.src.services.search.chunk_embed._get_code_chunker",
            side_effect=ImportError("chonkie[code] not installed"),
        ):
            content = "def test():\n    pass"
            with pytest.raises(ImportError):
                chunk_text(content, language="python")


class TestChunkerMode:
    """Tests for ChunkerMode enum."""

    def test_chunker_mode_values(self) -> None:
        """Should have expected mode values."""
        assert ChunkerMode.TOKEN == "token"
        assert ChunkerMode.CODE_AUTO == "code_auto"
        assert ChunkerMode.CODE_LANG_PYTHON == "code_lang_python"
        assert ChunkerMode.CODE_LANG_TYPESCRIPT == "code_lang_typescript"

    def test_chunker_mode_is_string(self) -> None:
        """ChunkerMode should be a StrEnum."""
        assert str(ChunkerMode.TOKEN) == "token"
        assert f"{ChunkerMode.CODE_AUTO}" == "code_auto"
