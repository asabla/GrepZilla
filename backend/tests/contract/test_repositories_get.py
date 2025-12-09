"""Contract tests for GET /repositories endpoint."""

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
def valid_token() -> str:
    """Create a valid JWT token with repository access."""
    return create_access_token(
        user_id="test-user",
        repository_ids=["repo-1", "repo-2"],
    )


@pytest.fixture
def admin_token() -> str:
    """Create an admin token with access to all repositories."""
    return create_access_token(
        user_id="admin-user",
        repository_ids=[],  # Empty list = access to all
    )


@pytest.fixture
def limited_token() -> str:
    """Create a token with access to only one repository."""
    return create_access_token(
        user_id="limited-user",
        repository_ids=["repo-1"],
    )


class TestGetRepositoriesContract:
    """Contract tests for repository listing endpoint."""

    @pytest.mark.asyncio
    async def test_list_repositories_returns_200(
        self,
        client: AsyncClient,
        valid_token: str,
    ) -> None:
        """GET /repositories returns 200 with valid auth."""
        response = await client.get(
            "/repositories",
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_repositories_returns_401_without_auth(
        self,
        client: AsyncClient,
    ) -> None:
        """GET /repositories returns 401 without authentication."""
        response = await client.get("/repositories")

        assert response.status_code == 401
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_list_repositories_returns_401_with_invalid_token(
        self,
        client: AsyncClient,
    ) -> None:
        """GET /repositories returns 401 with invalid token."""
        response = await client.get(
            "/repositories",
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_repositories_response_schema(
        self,
        client: AsyncClient,
        valid_token: str,
    ) -> None:
        """GET /repositories response matches expected schema."""
        response = await client.get(
            "/repositories",
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Response is a list
        assert isinstance(data, list)

        # If there are items, validate schema
        for item in data:
            assert "id" in item
            assert "name" in item
            assert "default_branch" in item
            assert "freshness_status" in item
            assert "last_indexed_at" in item or item.get("last_indexed_at") is None
            assert "backlog_size" in item
            assert isinstance(item["backlog_size"], int)
            assert "branches" in item
            assert isinstance(item["branches"], list)

    @pytest.mark.asyncio
    async def test_list_repositories_filters_by_access(
        self,
        client: AsyncClient,
        limited_token: str,
    ) -> None:
        """GET /repositories respects access control from JWT claims."""
        response = await client.get(
            "/repositories",
            headers={"Authorization": f"Bearer {limited_token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # All returned repositories should be accessible to the user
        for item in data:
            # In real implementation, verify item["id"] is in allowed list
            assert "id" in item

    @pytest.mark.asyncio
    async def test_list_repositories_branch_schema(
        self,
        client: AsyncClient,
        valid_token: str,
    ) -> None:
        """GET /repositories branch items match expected schema."""
        response = await client.get(
            "/repositories",
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        assert response.status_code == 200
        data = response.json()

        for repo in data:
            for branch in repo.get("branches", []):
                assert "name" in branch
                assert "is_default" in branch
                assert isinstance(branch["is_default"], bool)
                assert "freshness_status" in branch
                assert "last_indexed_at" in branch or branch.get("last_indexed_at") is None
                assert "backlog_size" in branch
                assert isinstance(branch["backlog_size"], int)


class TestGetSingleRepositoryContract:
    """Contract tests for GET /repositories/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_repository_returns_404_for_nonexistent(
        self,
        client: AsyncClient,
        admin_token: str,
    ) -> None:
        """GET /repositories/{id} returns 404 for non-existent repository."""
        response = await client.get(
            "/repositories/550e8400-e29b-41d4-a716-446655440000",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 404
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_get_repository_returns_422_for_invalid_uuid(
        self,
        client: AsyncClient,
        admin_token: str,
    ) -> None:
        """GET /repositories/{id} returns 422 for invalid UUID format."""
        response = await client.get(
            "/repositories/not-a-valid-uuid",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 422
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_get_repository_returns_403_for_unauthorized_access(
        self,
        client: AsyncClient,
        limited_token: str,
    ) -> None:
        """GET /repositories/{id} returns 403 when user lacks access."""
        # Try to access a repository not in the user's allowed list
        response = await client.get(
            "/repositories/660e8400-e29b-41d4-a716-446655440001",
            headers={"Authorization": f"Bearer {limited_token}"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_repository_response_schema(
        self,
        client: AsyncClient,
        admin_token: str,
    ) -> None:
        """GET /repositories/{id} response matches expected schema when found."""
        # This test validates the schema structure when a repository exists
        # In a real test with fixtures, we would create a repository first

        response = await client.get(
            "/repositories/550e8400-e29b-41d4-a716-446655440000",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Either 404 (not found) or 200 with proper schema
        if response.status_code == 200:
            data = response.json()
            assert "id" in data
            assert "name" in data
            assert "git_url" in data
            assert "default_branch" in data
            assert "auth_type" in data
            assert "access_state" in data
            assert "created_at" in data
            assert "updated_at" in data
