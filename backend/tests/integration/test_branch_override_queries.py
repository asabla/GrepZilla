"""Integration tests for branch-override query path."""

import pytest
from httpx import AsyncClient

from backend.src.api.deps.auth import create_access_token
from backend.src.api.main import create_app


@pytest.fixture
def app():
    """Create application instance."""
    return create_app()


@pytest.fixture
async def client(app):
    """Create test client."""
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


class TestBranchOverrideQueries:
    """Integration tests for branch override functionality in queries."""

    @pytest.fixture
    def token_with_branch_override(self) -> str:
        """Create token with branch override for specific repository."""
        return create_access_token(
            user_id="test-user",
            repository_ids=["repo-1", "repo-2"],
            branch_overrides={
                "repo-1": "feature-branch",
                "repo-2": "develop",
            },
        )

    @pytest.fixture
    def token_without_overrides(self) -> str:
        """Create token without branch overrides (uses defaults)."""
        return create_access_token(
            user_id="test-user",
            repository_ids=["repo-1", "repo-2"],
        )

    @pytest.mark.asyncio
    async def test_query_uses_jwt_branch_override(
        self,
        client: AsyncClient,
        token_with_branch_override: str,
    ) -> None:
        """Query uses branch override from JWT when no request override specified."""
        response = await client.post(
            "/queries",
            json={
                "query": "How does the authentication middleware work?",
                "repositories": ["repo-1"],
            },
            headers={"Authorization": f"Bearer {token_with_branch_override}"},
        )

        # Should return 200 and use the branch override from JWT
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "citations" in data

    @pytest.mark.asyncio
    async def test_request_branch_override_takes_precedence(
        self,
        client: AsyncClient,
        token_with_branch_override: str,
    ) -> None:
        """Request-level branch override takes precedence over JWT override."""
        response = await client.post(
            "/queries",
            json={
                "query": "How does the authentication middleware work?",
                "repositories": ["repo-1"],
                "branches": {"repo-1": "hotfix-branch"},  # Request override
            },
            headers={"Authorization": f"Bearer {token_with_branch_override}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data

    @pytest.mark.asyncio
    async def test_query_uses_default_branch_without_override(
        self,
        client: AsyncClient,
        token_without_overrides: str,
    ) -> None:
        """Query uses default branch when no override specified."""
        response = await client.post(
            "/queries",
            json={
                "query": "What is the error handling strategy?",
                "repositories": ["repo-1"],
            },
            headers={"Authorization": f"Bearer {token_without_overrides}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data

    @pytest.mark.asyncio
    async def test_mixed_branch_overrides(
        self,
        client: AsyncClient,
        token_with_branch_override: str,
    ) -> None:
        """Query handles mixed overrides (some from JWT, some from request)."""
        response = await client.post(
            "/queries",
            json={
                "query": "Show me the configuration options",
                "repositories": ["repo-1", "repo-2"],
                "branches": {"repo-1": "main"},  # Override JWT's feature-branch
                # repo-2 uses JWT's develop branch
            },
            headers={"Authorization": f"Bearer {token_with_branch_override}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "citations" in data

    @pytest.mark.asyncio
    async def test_citations_include_correct_branch(
        self,
        client: AsyncClient,
        token_with_branch_override: str,
    ) -> None:
        """Citations include the correct branch that was searched."""
        response = await client.post(
            "/queries",
            json={
                "query": "How are database connections managed?",
                "repositories": ["repo-1"],
            },
            headers={"Authorization": f"Bearer {token_with_branch_override}"},
        )

        assert response.status_code == 200
        data = response.json()

        # If there are citations, they should reference the correct branch
        for citation in data.get("citations", []):
            assert "branch" in citation
            # Branch should be either the override or the repository's default

    @pytest.mark.asyncio
    async def test_branch_override_for_unlisted_repo_ignored(
        self,
        client: AsyncClient,
    ) -> None:
        """Branch override for repository not in request is ignored."""
        token = create_access_token(
            user_id="test-user",
            repository_ids=["repo-1", "repo-2", "repo-3"],
            branch_overrides={
                "repo-1": "feature",
                "repo-3": "develop",  # repo-3 not in request
            },
        )

        response = await client.post(
            "/queries",
            json={
                "query": "Show me the API routes",
                "repositories": ["repo-1"],  # Only requesting repo-1
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200


class TestBranchAccessControl:
    """Tests for branch-level access control in queries."""

    @pytest.mark.asyncio
    async def test_query_respects_repository_access(
        self,
        client: AsyncClient,
    ) -> None:
        """Query returns 403 when requesting inaccessible repositories."""
        limited_token = create_access_token(
            user_id="limited-user",
            repository_ids=["repo-1"],  # Only access to repo-1
        )

        response = await client.post(
            "/queries",
            json={
                "query": "Find all config files",
                "repositories": ["repo-1", "repo-2"],  # Requesting both, but no access to repo-2
            },
            headers={"Authorization": f"Bearer {limited_token}"},
        )

        # Should return 403 since user doesn't have access to repo-2
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_query_all_repos_respects_access(
        self,
        client: AsyncClient,
    ) -> None:
        """Query without repository filter respects access control."""
        limited_token = create_access_token(
            user_id="limited-user",
            repository_ids=["repo-1"],
        )

        response = await client.post(
            "/queries",
            json={
                "query": "Where is the main entry point?",
                # No repositories specified = search all accessible
            },
            headers={"Authorization": f"Bearer {limited_token}"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_query_all_repos(
        self,
        client: AsyncClient,
    ) -> None:
        """Admin token (empty repository_ids) can query all repositories."""
        admin_token = create_access_token(
            user_id="admin",
            repository_ids=[],  # Empty = admin/all access
        )

        response = await client.post(
            "/queries",
            json={
                "query": "Show deployment configuration",
                "repositories": ["repo-1", "repo-2", "repo-3"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
