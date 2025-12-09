"""Prompt and context builder for Q&A queries."""

from typing import Any

from backend.src.config.constants import CHUNK_SIZE_TOKENS
from backend.src.config.logging import get_logger
from backend.src.services.search.search_pipeline import SearchResult

logger = get_logger(__name__)


class PromptBuilder:
    """Builds prompts and context for LLM-based Q&A."""

    def __init__(
        self,
        max_context_tokens: int = 8000,
    ) -> None:
        """Initialize prompt builder.

        Args:
            max_context_tokens: Maximum tokens for context.
        """
        self.max_context_tokens = max_context_tokens

    def build_context(
        self,
        search_results: list[SearchResult],
    ) -> str:
        """Build context string from search results.

        Args:
            search_results: List of search results to include.

        Returns:
            Formatted context string for LLM.
        """
        if not search_results:
            return ""

        context_parts: list[str] = []
        estimated_tokens = 0

        for i, result in enumerate(search_results):
            # Estimate tokens in this chunk
            chunk_tokens = len(result.content.split()) * 1.3  # Rough estimate

            # Check if adding this chunk would exceed limit
            if estimated_tokens + chunk_tokens > self.max_context_tokens:
                logger.debug(
                    "Context limit reached",
                    chunks_included=i,
                    estimated_tokens=estimated_tokens,
                )
                break

            # Format the chunk with metadata
            chunk_context = self._format_chunk(result, i + 1)
            context_parts.append(chunk_context)
            estimated_tokens += chunk_tokens

        return "\n\n".join(context_parts)

    def _format_chunk(
        self,
        result: SearchResult,
        index: int,
    ) -> str:
        """Format a single search result for context.

        Args:
            result: Search result to format.
            index: 1-based index for reference.

        Returns:
            Formatted context block.
        """
        header = f"[{index}] File: {result.path}"
        if result.language:
            header += f" ({result.language})"
        header += f" - Lines {result.line_start}-{result.line_end}"

        return f"{header}\n```\n{result.content}\n```"

    def build_system_prompt(self) -> str:
        """Build system prompt for Q&A.

        Returns:
            System prompt string.
        """
        return """You are a code analysis assistant. Your role is to answer questions 
about codebases using the provided context from indexed code files.

Guidelines:
1. Base your answers only on the provided code context
2. Reference specific files and line numbers when citing code
3. If the context doesn't contain enough information, say so clearly
4. Explain code behavior in clear, technical terms
5. Focus on the specific question asked

When answering about middleware, authentication, or other cross-cutting concerns:
- Identify the main components involved
- Explain the flow of execution
- Highlight any configuration or environment dependencies
- Note any error handling patterns"""

    def build_user_prompt(
        self,
        query: str,
        context: str,
    ) -> str:
        """Build user prompt with query and context.

        Args:
            query: User's question.
            context: Formatted context from search results.

        Returns:
            Complete user prompt.
        """
        if not context:
            return f"""Question: {query}

Note: No relevant code was found in the indexed repositories. 
Please rephrase your question or verify the repository scope."""

        return f"""Based on the following code context, please answer the question.

CODE CONTEXT:
{context}

QUESTION: {query}

Please provide a clear, technical answer referencing the relevant files and line numbers."""

    def build_full_prompt(
        self,
        query: str,
        search_results: list[SearchResult],
    ) -> dict[str, str]:
        """Build complete prompt for LLM API.

        Args:
            query: User's question.
            search_results: Search results for context.

        Returns:
            Dict with 'system' and 'user' prompt keys.
        """
        context = self.build_context(search_results)

        return {
            "system": self.build_system_prompt(),
            "user": self.build_user_prompt(query, context),
        }
