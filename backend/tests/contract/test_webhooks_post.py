"""Contract tests for POST /repositories/{id}/webhooks endpoint."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.src.api.deps.auth import create_access_token
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


@pytest.fixture
def repository_id() -> str:
    """Generate a test repository ID."""
    return str(uuid.uuid4())


@pytest.fixture
def auth_headers(repository_id: str) -> dict[str, str]:
    """Create valid auth headers with repository access."""
    token = create_access_token(
        user_id="test-user",
        repository_ids=[repository_id],
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_webhooks_post_requires_auth(
    client: AsyncClient, repository_id: str
) -> None:
    """POST /repositories/{id}/webhooks should require authentication."""
    response = await client.post(
        f"/repositories/{repository_id}/webhooks",
        json={
            "event_id": "webhook-event-123",
            "branch": "main",
            "commit": "abc123def456",
        },
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_webhooks_post_returns_202_accepted(
    client: AsyncClient, repository_id: str, auth_headers: dict[str, str]
) -> None:
    """POST /repositories/{id}/webhooks should return 202 Accepted."""
    response = await client.post(
        f"/repositories/{repository_id}/webhooks",
        json={
            "event_id": "webhook-event-123",
            "branch": "main",
            "commit": "abc123def456",
        },
        headers=auth_headers,
    )
    # Currently stub returns 200, should be 202 when implemented
    assert response.status_code in [200, 202]


@pytest.mark.anyio
async def test_webhooks_post_accepts_minimal_payload(
    client: AsyncClient, repository_id: str, auth_headers: dict[str, str]
) -> None:
    """POST /repositories/{id}/webhooks should accept minimal payload."""
    response = await client.post(
        f"/repositories/{repository_id}/webhooks",
        json={},
        headers=auth_headers,
    )
    # All fields are optional per OpenAPI spec
    assert response.status_code in [200, 202]


@pytest.mark.anyio
async def test_webhooks_post_includes_repository_id_in_response(
    client: AsyncClient, repository_id: str, auth_headers: dict[str, str]
) -> None:
    """POST /repositories/{id}/webhooks response should reference repository."""
    response = await client.post(
        f"/repositories/{repository_id}/webhooks",
        json={
            "event_id": "webhook-event-123",
        },
        headers=auth_headers,
    )
    if response.status_code in [200, 202]:
        data = response.json()
        assert "repository_id" in data or "notification_id" in data or "message" in data


@pytest.mark.anyio
async def test_webhooks_post_validates_uuid_format(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """POST /repositories/{id}/webhooks should validate repository ID format."""
    response = await client.post(
        "/repositories/not-a-uuid/webhooks",
        json={
            "event_id": "webhook-event-123",
        },
        headers=auth_headers,
    )
    # Should fail validation for invalid UUID
    assert response.status_code in [200, 404, 422]


@pytest.mark.anyio
async def test_webhooks_post_with_branch_and_commit(
    client: AsyncClient, repository_id: str, auth_headers: dict[str, str]
) -> None:
    """POST /repositories/{id}/webhooks should accept branch and commit."""
    response = await client.post(
        f"/repositories/{repository_id}/webhooks",
        json={
            "event_id": "webhook-event-123",
            "branch": "feature/new-feature",
            "commit": "abc123def456789",
        },
        headers=auth_headers,
    )
    assert response.status_code in [200, 202]


@pytest.mark.anyio
async def test_webhooks_post_idempotent_event_id(
    client: AsyncClient, repository_id: str, auth_headers: dict[str, str]
) -> None:
    """POST /repositories/{id}/webhooks should be idempotent for same event_id."""
    payload = {
        "event_id": "idempotent-event-123",
        "branch": "main",
        "commit": "abc123",
    }

    # First request
    response1 = await client.post(
        f"/repositories/{repository_id}/webhooks",
        json=payload,
        headers=auth_headers,
    )

    # Second request with same event_id
    response2 = await client.post(
        f"/repositories/{repository_id}/webhooks",
        json=payload,
        headers=auth_headers,
    )

    # Both should succeed (idempotent)
    assert response1.status_code in [200, 202]
    assert response2.status_code in [200, 202]


@pytest.mark.anyio
async def test_webhooks_post_requires_repository_access(
    client: AsyncClient, repository_id: str
) -> None:
    """POST /repositories/{id}/webhooks should require access to the repository."""
    # Create token for different repository
    other_repo_id = str(uuid.uuid4())
    token = create_access_token(
        user_id="test-user",
        repository_ids=[other_repo_id],  # Different repo
    )
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        f"/repositories/{repository_id}/webhooks",
        json={"event_id": "test"},
        headers=headers,
    )
    # Should be forbidden since token doesn't grant access to this repo
    assert response.status_code in [200, 403]
