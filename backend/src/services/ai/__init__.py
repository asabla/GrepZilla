"""AI services for LLM, embeddings, and agents."""

from backend.src.services.ai.embeddings import EmbeddingClient, get_embedding_client
from backend.src.services.ai.llm import LLMClient, get_llm_client


# Lazy imports for heavy modules (LiteLLM via OpenAI Agents SDK)
# This prevents Celery workers from loading these at fork time
def get_agent_client():
    """Get singleton agent client instance (lazy import)."""
    from backend.src.services.ai.agent import get_agent_client as _get

    return _get()


def get_AgentClient():
    """Get AgentClient class (lazy import)."""
    from backend.src.services.ai.agent import AgentClient

    return AgentClient


def reset_agent_client():
    """Reset the agent client singleton (lazy import)."""
    from backend.src.services.ai.agent import reset_agent_client as _reset

    return _reset()


__all__ = [
    "EmbeddingClient",
    "LLMClient",
    "get_agent_client",
    "get_embedding_client",
    "get_llm_client",
    "reset_agent_client",
]
