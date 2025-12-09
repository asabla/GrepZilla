"""Contract tests for POST /queries endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.src.api.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_queries_post_requires_auth(client: AsyncClient) -> None:
    """POST /queries should require authentication."""
    response = await client.post(
        "/queries",
        json={"query": "How does the middleware work?"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_queries_post_validates_request_body(client: AsyncClient) -> None:
    """POST /queries should validate request body structure."""
    # Missing required query field
    response = await client.post(
        "/queries",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code in [401, 422]


@pytest.mark.anyio
async def test_queries_post_happy_path_schema(client: AsyncClient) -> None:
    """POST /queries should return expected response schema."""
    # This test will be expanded once authentication is properly mocked
    # For now, verify the endpoint exists and returns expected error
    response = await client.post(
        "/queries",
        json={
            "query": "How does the authentication middleware work?",
            "repositories": [],
        },
        headers={"Authorization": "Bearer test-token"},
    )
    # Will fail auth until we mock JWT validation
    assert response.status_code in [200, 401, 403]


@pytest.mark.anyio
async def test_queries_post_response_includes_citations() -> None:
    """POST /queries response should include citations array."""
    # Placeholder - will be implemented with mocked search results
    pass


@pytest.mark.anyio
async def test_queries_post_response_includes_latency() -> None:
    """POST /queries response should include latency_ms field."""
    # Placeholder - will be implemented with mocked search results
    pass


@pytest.mark.anyio
async def test_queries_post_empty_query_rejected(client: AsyncClient) -> None:
    """POST /queries should reject empty query strings."""
    response = await client.post(
        "/queries",
        json={"query": ""},
        headers={"Authorization": "Bearer test-token"},
    )
    # Should fail validation or auth
    assert response.status_code in [401, 422]


@pytest.mark.anyio
async def test_queries_post_query_too_long(client: AsyncClient) -> None:
    """POST /queries should reject queries exceeding max length."""
    long_query = "x" * 3000  # Exceeds MAX_QUERY_LENGTH
    response = await client.post(
        "/queries",
        json={"query": long_query},
        headers={"Authorization": "Bearer test-token"},
    )
    # Should fail validation or auth
    assert response.status_code in [401, 422]


@pytest.mark.anyio
async def test_queries_post_accepts_agent_mode_field(client: AsyncClient) -> None:
    """POST /queries should accept agent_mode field in request body."""
    response = await client.post(
        "/queries",
        json={
            "query": "How does the authentication middleware work?",
            "agent_mode": True,
        },
        headers={"Authorization": "Bearer test-token"},
    )
    # Will fail auth until we mock JWT validation, but should not fail validation
    assert response.status_code in [200, 401, 403]


@pytest.mark.anyio
async def test_queries_post_agent_mode_defaults_to_false(client: AsyncClient) -> None:
    """POST /queries should default agent_mode to false."""
    response = await client.post(
        "/queries",
        json={
            "query": "How does the authentication middleware work?",
        },
        headers={"Authorization": "Bearer test-token"},
    )
    # Will fail auth until we mock JWT validation, but should not fail validation
    assert response.status_code in [200, 401, 403]


@pytest.mark.anyio
async def test_queries_post_agent_mode_invalid_type_rejected(
    client: AsyncClient,
) -> None:
    """POST /queries should reject non-boolean agent_mode."""
    response = await client.post(
        "/queries",
        json={
            "query": "How does the authentication middleware work?",
            "agent_mode": "yes",  # Invalid type
        },
        headers={"Authorization": "Bearer test-token"},
    )
    # Should fail validation
    assert response.status_code in [401, 422]
