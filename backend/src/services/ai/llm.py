"""LLM client for OpenAI-compatible APIs."""

from dataclasses import dataclass
from typing import Any

import httpx

from backend.src.config.logging import get_logger
from backend.src.config.settings import get_settings

logger = get_logger(__name__)


@dataclass
class ChatMessage:
    """A chat message."""

    role: str  # "system", "user", or "assistant"
    content: str


@dataclass
class ChatCompletionResponse:
    """Response from a chat completion request."""

    content: str
    model: str
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMClient:
    """Client for OpenAI-compatible LLM APIs.

    Supports OpenAI, Ollama, Azure OpenAI, and other compatible providers.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout: int | None = None,
    ) -> None:
        """Initialize LLM client.

        Args:
            base_url: API base URL. Defaults to settings.
            api_key: API key. Defaults to settings.
            model: Model name. Defaults to settings.
            max_tokens: Max response tokens. Defaults to settings.
            temperature: Sampling temperature. Defaults to settings.
            timeout: Request timeout in seconds. Defaults to settings.
        """
        settings = get_settings()

        self.base_url = (base_url or settings.llm_api_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.max_tokens = max_tokens or settings.llm_max_tokens
        self.temperature = (
            temperature if temperature is not None else settings.llm_temperature
        )
        self.timeout = timeout or settings.llm_timeout

        # API key is optional for local servers like Ollama
        if api_key:
            self.api_key = api_key
        elif settings.llm_api_key:
            self.api_key = settings.llm_api_key.get_secret_value()
        else:
            self.api_key = None

        logger.info(
            "LLM client initialized",
            base_url=self.base_url,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

    def _get_headers(self) -> dict[str, str]:
        """Get request headers."""
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatCompletionResponse:
        """Create a chat completion.

        Args:
            messages: List of chat messages.
            model: Override model for this request.
            max_tokens: Override max tokens for this request.
            temperature: Override temperature for this request.

        Returns:
            ChatCompletionResponse with generated content.

        Raises:
            httpx.HTTPError: If the request fails.
        """
        url = f"{self.base_url}/chat/completions"

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
        }

        logger.debug(
            "Sending chat completion request",
            model=payload["model"],
            message_count=len(messages),
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        # Parse response
        choice = data["choices"][0]
        usage = data.get("usage", {})

        result = ChatCompletionResponse(
            content=choice["message"]["content"],
            model=data.get("model", self.model),
            finish_reason=choice.get("finish_reason"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )

        logger.debug(
            "Chat completion received",
            model=result.model,
            finish_reason=result.finish_reason,
            total_tokens=result.total_tokens,
        )

        return result

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Simple completion helper.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.
            model: Override model for this request.
            max_tokens: Override max tokens.
            temperature: Override temperature.

        Returns:
            Generated text content.
        """
        messages = []
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        messages.append(ChatMessage(role="user", content=prompt))

        response = await self.chat_completion(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.content

    async def health_check(self) -> bool:
        """Check if the LLM service is reachable.

        Returns:
            True if service is healthy.
        """
        try:
            # Try to list models (common endpoint)
            url = f"{self.base_url}/models"
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url, headers=self._get_headers())
                return response.status_code == 200
        except Exception as e:
            logger.warning("LLM health check failed", error=str(e))
            return False


# Client singleton
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get LLM client singleton.

    Returns:
        LLMClient instance.
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def reset_llm_client() -> None:
    """Reset the LLM client singleton (for testing)."""
    global _llm_client
    _llm_client = None
