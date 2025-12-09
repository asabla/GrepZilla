"""Embeddings client for OpenAI-compatible APIs."""

from dataclasses import dataclass

import httpx

from backend.src.config.logging import get_logger
from backend.src.config.settings import get_settings

logger = get_logger(__name__)


@dataclass
class EmbeddingResult:
    """Result of an embedding request."""

    embeddings: list[list[float]]
    model: str
    total_tokens: int | None = None


class EmbeddingClient:
    """Client for OpenAI-compatible embedding APIs.

    Supports OpenAI, Ollama, and other compatible providers.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        batch_size: int | None = None,
        timeout: int = 60,
    ) -> None:
        """Initialize embedding client.

        Args:
            base_url: API base URL. Defaults to settings.
            api_key: API key. Defaults to settings.
            model: Model name. Defaults to settings.
            dimensions: Embedding dimensions. Defaults to settings.
            batch_size: Batch size for requests. Defaults to settings.
            timeout: Request timeout in seconds.
        """
        settings = get_settings()

        self.base_url = (base_url or settings.effective_embedding_api_base_url).rstrip(
            "/"
        )
        self.model = model or settings.embedding_model
        self.dimensions = dimensions or settings.embedding_dimensions
        self.batch_size = batch_size or settings.embedding_batch_size
        self.timeout = timeout

        # API key is optional for local servers like Ollama
        effective_key = settings.effective_embedding_api_key
        if api_key:
            self.api_key = api_key
        elif effective_key:
            self.api_key = effective_key.get_secret_value()
        else:
            self.api_key = None

        self.enabled = settings.embedding_enabled

        logger.info(
            "Embedding client initialized",
            base_url=self.base_url,
            model=self.model,
            dimensions=self.dimensions,
            batch_size=self.batch_size,
            enabled=self.enabled,
        )

    def _get_headers(self) -> dict[str, str]:
        """Get request headers."""
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def embed(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> EmbeddingResult:
        """Generate embeddings for texts.

        Args:
            texts: List of texts to embed.
            model: Override model for this request.

        Returns:
            EmbeddingResult with embedding vectors.

        Raises:
            httpx.HTTPError: If the request fails.
        """
        if not self.enabled:
            logger.debug("Embeddings disabled, returning empty result")
            return EmbeddingResult(
                embeddings=[[] for _ in texts],
                model=model or self.model,
                total_tokens=0,
            )

        if not texts:
            return EmbeddingResult(
                embeddings=[],
                model=model or self.model,
                total_tokens=0,
            )

        url = f"{self.base_url}/embeddings"

        payload: dict = {
            "model": model or self.model,
            "input": texts,
        }

        # Add dimensions if specified (OpenAI text-embedding-3 supports this)
        if self.dimensions:
            payload["dimensions"] = self.dimensions

        logger.debug(
            "Sending embedding request",
            model=payload["model"],
            text_count=len(texts),
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        # Parse response - embeddings are returned in order
        embeddings = [
            item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])
        ]
        usage = data.get("usage", {})

        result = EmbeddingResult(
            embeddings=embeddings,
            model=data.get("model", self.model),
            total_tokens=usage.get("total_tokens"),
        )

        logger.debug(
            "Embeddings received",
            model=result.model,
            embedding_count=len(result.embeddings),
            total_tokens=result.total_tokens,
        )

        return result

    async def embed_single(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed.
            model: Override model for this request.

        Returns:
            Embedding vector.
        """
        result = await self.embed([text], model=model)
        return result.embeddings[0] if result.embeddings else []

    async def embed_batch(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> list[list[float]]:
        """Generate embeddings in batches.

        Args:
            texts: List of texts to embed.
            model: Override model for this request.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            result = await self.embed(batch, model=model)
            all_embeddings.extend(result.embeddings)

            logger.debug(
                "Batch embeddings complete",
                batch_index=i // self.batch_size,
                batch_size=len(batch),
                total_processed=len(all_embeddings),
            )

        return all_embeddings

    async def health_check(self) -> bool:
        """Check if the embedding service is reachable.

        Returns:
            True if service is healthy.
        """
        if not self.enabled:
            return True

        try:
            # Try a simple embedding request
            result = await self.embed(["test"])
            return len(result.embeddings) > 0 and len(result.embeddings[0]) > 0
        except Exception as e:
            logger.warning("Embedding health check failed", error=str(e))
            return False


# Client singleton
_embedding_client: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    """Get embedding client singleton.

    Returns:
        EmbeddingClient instance.
    """
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client


def reset_embedding_client() -> None:
    """Reset the embedding client singleton (for testing)."""
    global _embedding_client
    _embedding_client = None
