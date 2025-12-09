"""OpenAI Agents SDK client for agentic query processing."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from agents import Agent, ModelSettings, Runner, function_tool
from agents.run import RunResult

from backend.src.config.logging import get_logger
from backend.src.config.settings import get_settings
from backend.src.services.search.search_pipeline import SearchPipeline, SearchResult

if TYPE_CHECKING:
    from agents.extensions.models.litellm_model import LitellmModel

logger = get_logger(__name__)


def create_search_tool(
    repository_ids: list[str],
    branch_overrides: dict[str, str],
) -> Any:
    """Create a search_codebase function tool with bound repository context.

    Args:
        repository_ids: List of repository IDs to search.
        branch_overrides: Map of repo_id -> branch_id overrides.

    Returns:
        A function_tool-decorated search function.
    """

    @function_tool
    def search_codebase(query: str) -> list[dict[str, Any]]:
        """Search the codebase for relevant code snippets.

        Use this tool to find code, documentation, and configuration files
        that are relevant to answering the user's question.

        Args:
            query: Natural language search query describing what to find.

        Returns:
            List of code snippets with file paths, line numbers, and content.
        """
        pipeline = SearchPipeline(
            repository_ids=repository_ids,
            branch_overrides=branch_overrides,
        )

        results = pipeline.search_with_context(query)

        # Convert to serializable format for the agent
        return [
            {
                "path": r.path,
                "repository": r.repository_id,
                "branch": r.branch_id,
                "line_start": r.line_start,
                "line_end": r.line_end,
                "language": r.language,
                "content": r.content,
                "score": r.score,
            }
            for r in results
        ]

    return search_codebase


class AgentClient:
    """Client for running agentic queries using OpenAI Agents SDK."""

    def __init__(
        self,
        model: str | None = None,
        max_turns: int | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialize agent client.

        Args:
            model: Model name for agent. Defaults to settings.llm_model.
            max_turns: Maximum agent turns. Defaults to settings.
            api_key: API key for the LLM provider. Defaults to settings.llm_api_key.
            base_url: Base URL for OpenAI-compatible API. Defaults to settings.llm_api_base_url.
        """
        settings = get_settings()

        self.model_name = model or settings.llm_model
        self.max_turns = max_turns or settings.agent_max_turns
        self.base_url = (base_url or settings.llm_api_base_url).rstrip("/")

        # Resolve API key (same pattern as LLMClient)
        if api_key:
            self.api_key = api_key
        elif settings.llm_api_key:
            self.api_key = settings.llm_api_key.get_secret_value()
        else:
            self.api_key = None

        # Create LitellmModel for provider-agnostic LLM access
        # Import lazily to avoid heavy initialization at module load time
        # (which can cause issues with Celery worker fork pools)
        from agents.extensions.models.litellm_model import LitellmModel

        # For OpenAI-compatible APIs with custom base_url, we use openai/ prefix.
        # LiteLLM requires an API key even for local APIs, so we provide a
        # placeholder when none is configured (e.g., for Ollama).
        effective_api_key = self.api_key if self.api_key else "not-needed"

        self.model = LitellmModel(
            model=f"openai/{self.model_name}",
            api_key=effective_api_key,
            base_url=self.base_url,
        )

        logger.info(
            "Agent client initialized",
            model=self.model_name,
            max_turns=self.max_turns,
            base_url=self.base_url,
        )

    def _build_system_instructions(self) -> str:
        """Build system instructions for the code analysis agent.

        Returns:
            System instructions string.
        """
        return """You are a code analysis assistant with access to a codebase search tool.

Your role is to answer questions about code by:
1. Using the search_codebase tool to find relevant code snippets
2. Analyzing the retrieved code to understand how it works
3. Providing clear, accurate answers with references to specific files and line numbers

Guidelines:
- Always use the search tool to find relevant code before answering
- You may call the search tool multiple times with different queries to gather comprehensive context
- Reference specific files and line numbers when citing code
- If you cannot find enough information, clearly state what's missing
- Focus on the specific question asked
- Be technical and precise in your explanations

When answering:
- Start by searching for the most relevant code
- If needed, search for related implementations, tests, or documentation
- Synthesize findings into a coherent answer
- Include file paths and line numbers for all code references"""

    async def run_agent(
        self,
        query: str,
        repository_ids: list[str],
        branch_overrides: dict[str, str],
    ) -> RunResult:
        """Run the agent to answer a query.

        Args:
            query: User's question about the codebase.
            repository_ids: List of repository IDs to search.
            branch_overrides: Map of repo_id -> branch_id overrides.

        Returns:
            RunResult containing the agent's response and execution details.
        """
        # Create search tool bound to this query's repository context
        search_tool = create_search_tool(repository_ids, branch_overrides)

        # Create agent with search tool and LiteLLM model for provider-agnostic access
        agent = Agent(
            name="CodeAnalyst",
            instructions=self._build_system_instructions(),
            model=self.model,
            model_settings=ModelSettings(include_usage=True),
            tools=[search_tool],
        )

        logger.debug(
            "Running agent",
            query=query[:100],
            repository_count=len(repository_ids),
        )

        # Run the agent
        result = await Runner.run(
            agent,
            input=query,
            max_turns=self.max_turns,
        )

        logger.debug(
            "Agent completed",
            final_output_length=len(result.final_output) if result.final_output else 0,
        )

        return result

    def extract_citations_from_result(
        self,
        result: RunResult[str],
    ) -> list[SearchResult]:
        """Extract citations from agent tool calls.

        Parses the agent's tool call history to find all search results
        that were returned during the agent's execution.

        Args:
            result: The agent run result.

        Returns:
            List of SearchResult objects from tool calls.
        """
        citations: list[SearchResult] = []
        seen_keys: set[tuple[str, str, str, int, int]] = set()

        # Iterate through the run's raw responses to find tool outputs
        for item in result.raw_responses:
            # Check if this response contains tool call results
            if hasattr(item, "output") and isinstance(item.output, list):
                for output_item in item.output:
                    if hasattr(output_item, "output") and isinstance(
                        output_item.output, str
                    ):
                        # Try to parse as search results
                        try:
                            search_data = json.loads(output_item.output)
                            if isinstance(search_data, list):
                                for hit in search_data:
                                    key = (
                                        hit.get("repository", ""),
                                        hit.get("branch", ""),
                                        hit.get("path", ""),
                                        hit.get("line_start", 0),
                                        hit.get("line_end", 0),
                                    )
                                    if key not in seen_keys:
                                        seen_keys.add(key)
                                        citations.append(
                                            SearchResult(
                                                chunk_id="",
                                                content=hit.get("content", ""),
                                                path=hit.get("path", ""),
                                                repository_id=hit.get("repository", ""),
                                                branch_id=hit.get("branch", ""),
                                                line_start=hit.get("line_start", 1),
                                                line_end=hit.get("line_end", 1),
                                                language=hit.get("language"),
                                                score=hit.get("score", 0.0),
                                            )
                                        )
                        except (json.JSONDecodeError, TypeError):
                            continue

        return citations


# Singleton instance
_agent_client: AgentClient | None = None


def get_agent_client() -> AgentClient:
    """Get singleton agent client instance.

    Returns:
        AgentClient instance.
    """
    global _agent_client
    if _agent_client is None:
        _agent_client = AgentClient()
    return _agent_client


def reset_agent_client() -> None:
    """Reset the agent client singleton (for testing)."""
    global _agent_client
    _agent_client = None
