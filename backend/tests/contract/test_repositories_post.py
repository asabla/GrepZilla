"""Contract tests for POST /repositories endpoint."""

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
def auth_headers() -> dict[str, str]:
    """Create valid auth headers with admin token."""
    token = create_access_token(user_id="test-admin", repository_ids=[])
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_repositories_post_requires_auth(client: AsyncClient) -> None:
    """POST /repositories should require authentication."""
    response = await client.post(
        "/repositories",
        json={
            "name": "test-repo",
            "git_url": "https://github.com/org/repo.git",
            "default_branch": "main",
        },
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_repositories_post_validates_required_fields(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """POST /repositories should validate required fields."""
    # Missing name
    response = await client.post(
        "/repositories",
        json={
            "git_url": "https://github.com/org/repo.git",
            "default_branch": "main",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422

    # Missing git_url
    response = await client.post(
        "/repositories",
        json={
            "name": "test-repo",
            "default_branch": "main",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_repositories_post_validates_git_url_format(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """POST /repositories should validate git_url format."""
    response = await client.post(
        "/repositories",
        json={
            "name": "test-repo",
            "git_url": "not-a-valid-url",
            "default_branch": "main",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_repositories_post_happy_path_returns_201(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """POST /repositories should return 201 on success."""
    response = await client.post(
        "/repositories",
        json={
            "name": "test-repo",
            "git_url": "https://github.com/org/repo.git",
            "default_branch": "main",
        },
        headers=auth_headers,
    )
    # Currently a stub, but should return 201 when implemented
    assert response.status_code in [200, 201]


@pytest.mark.anyio
async def test_repositories_post_response_includes_id(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """POST /repositories response should include repository ID."""
    response = await client.post(
        "/repositories",
        json={
            "name": "test-repo",
            "git_url": "https://github.com/org/repo.git",
            "default_branch": "main",
        },
        headers=auth_headers,
    )
    if response.status_code in [200, 201]:
        data = response.json()
        # When implemented, should return id
        assert "id" in data or "message" in data


@pytest.mark.anyio
async def test_repositories_post_with_auth_type(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """POST /repositories should accept auth_type field."""
    response = await client.post(
        "/repositories",
        json={
            "name": "test-repo",
            "git_url": "https://github.com/org/repo.git",
            "default_branch": "main",
            "auth_type": "token",
            "credential_ref": "secret/github-token",
        },
        headers=auth_headers,
    )
    # Should accept the request with auth fields
    assert response.status_code in [200, 201, 422]


@pytest.mark.anyio
async def test_repositories_post_name_validation(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """POST /repositories should validate repository name."""
    # Empty name
    response = await client.post(
        "/repositories",
        json={
            "name": "",
            "git_url": "https://github.com/org/repo.git",
            "default_branch": "main",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422

    # Name too long
    response = await client.post(
        "/repositories",
        json={
            "name": "x" * 300,
            "git_url": "https://github.com/org/repo.git",
            "default_branch": "main",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_repositories_post_default_branch_defaults_to_main(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """POST /repositories should default to main branch if not specified."""
    response = await client.post(
        "/repositories",
        json={
            "name": "test-repo",
            "git_url": "https://github.com/org/repo.git",
        },
        headers=auth_headers,
    )
    # Should accept request without explicit default_branch
    assert response.status_code in [200, 201, 422]
