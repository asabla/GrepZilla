"""Access control helper for applying repo/branch claims to queries."""

from typing import TypedDict

from backend.src.api.deps.auth import TokenClaims
from backend.src.config.logging import get_logger

logger = get_logger(__name__)


class AccessContext(TypedDict):
    """Context for access-controlled operations."""

    user_id: str
    allowed_repositories: list[str]
    branch_overrides: dict[str, str]
    is_admin: bool


class AccessControlService:
    """Service for access control checks and filtering."""

    def get_access_context(self, claims: TokenClaims) -> AccessContext:
        """Build access context from JWT claims.

        Args:
            claims: Token claims with user info and scope.

        Returns:
            AccessContext with resolved permissions.
        """
        # Empty repository_ids means admin/service token with full access
        is_admin = len(claims.repository_ids) == 0

        return AccessContext(
            user_id=claims.sub,
            allowed_repositories=claims.repository_ids,
            branch_overrides=claims.branch_overrides,
            is_admin=is_admin,
        )

    def filter_repositories(
        self,
        requested: list[str] | None,
        context: AccessContext,
    ) -> list[str]:
        """Filter requested repositories by access control.

        Args:
            requested: Repository IDs requested by user.
            context: Access context from JWT.

        Returns:
            List of accessible repository IDs.
        """
        # Admin has access to all
        if context["is_admin"]:
            return requested or []

        allowed = set(context["allowed_repositories"])

        if not requested:
            # No specific request = all allowed repositories
            return list(allowed)

        # Intersection of requested and allowed
        filtered = [r for r in requested if r in allowed]

        if len(filtered) < len(requested or []):
            logger.debug(
                "Some repositories filtered by access control",
                requested=len(requested or []),
                allowed=len(filtered),
                user_id=context["user_id"],
            )

        return filtered

    def check_repository_access(
        self,
        repository_id: str,
        context: AccessContext,
    ) -> bool:
        """Check if user has access to a specific repository.

        Args:
            repository_id: Repository ID to check.
            context: Access context from JWT.

        Returns:
            True if user has access, False otherwise.
        """
        if context["is_admin"]:
            return True

        return repository_id in context["allowed_repositories"]

    def get_effective_branch(
        self,
        repository_id: str,
        request_override: str | None,
        context: AccessContext,
    ) -> str | None:
        """Get effective branch for a repository, applying overrides.

        Priority order:
        1. Request-level override (from query parameters)
        2. JWT-level override (from token claims)
        3. None (use repository's default branch)

        Args:
            repository_id: Repository ID.
            request_override: Branch override from request.
            context: Access context with JWT overrides.

        Returns:
            Branch name to use, or None for default.
        """
        # Request override takes priority
        if request_override:
            return request_override

        # JWT override from claims
        return context["branch_overrides"].get(repository_id)

    def merge_branch_overrides(
        self,
        request_overrides: dict[str, str] | None,
        context: AccessContext,
    ) -> dict[str, str]:
        """Merge request and JWT branch overrides.

        Request overrides take precedence over JWT overrides.

        Args:
            request_overrides: Branch overrides from request.
            context: Access context with JWT overrides.

        Returns:
            Merged branch overrides.
        """
        # Start with JWT overrides
        merged = dict(context["branch_overrides"])

        # Request overrides take precedence
        if request_overrides:
            merged.update(request_overrides)

        return merged

    def validate_branch_access(
        self,
        repository_id: str,
        branch: str,
        context: AccessContext,
    ) -> bool:
        """Validate that user can access a specific branch.

        For now, branch-level access is not restricted beyond
        repository access. This method exists for future
        fine-grained branch permissions.

        Args:
            repository_id: Repository ID.
            branch: Branch name.
            context: Access context.

        Returns:
            True if access is allowed.
        """
        # First check repository access
        if not self.check_repository_access(repository_id, context):
            return False

        # Branch-level restrictions could be added here
        # For now, repository access grants branch access
        return True


# Singleton instance
_access_control_service: AccessControlService | None = None


def get_access_control_service() -> AccessControlService:
    """Get access control service singleton.

    Returns:
        AccessControlService instance.
    """
    global _access_control_service
    if _access_control_service is None:
        _access_control_service = AccessControlService()
    return _access_control_service
