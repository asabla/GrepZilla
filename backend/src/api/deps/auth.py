"""JWT authentication dependency for FastAPI."""

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from backend.src.config.settings import get_settings

# Security scheme for OpenAPI docs
security = HTTPBearer(auto_error=True)


class TokenClaims(BaseModel):
    """JWT token claims with repository/branch access scope."""

    sub: str = Field(..., description="User identifier")
    exp: datetime = Field(..., description="Token expiration time")
    iat: datetime = Field(..., description="Token issued at time")
    repository_ids: list[str] = Field(
        default_factory=list,
        description="List of repository IDs the user can access",
    )
    branch_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Map of repo_id -> branch name for branch-specific access",
    )


def create_access_token(
    user_id: str,
    repository_ids: list[str] | None = None,
    branch_overrides: dict[str, str] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token.

    Args:
        user_id: User identifier to embed in token.
        repository_ids: List of repository IDs the user can access.
        branch_overrides: Map of repo_id -> branch for branch-specific access.
        expires_delta: Custom expiration time delta.

    Returns:
        Encoded JWT token string.
    """
    settings = get_settings()

    now = datetime.now(timezone.utc)
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)

    claims: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + expires_delta,
        "repository_ids": repository_ids or [],
        "branch_overrides": branch_overrides or {},
    }

    return jwt.encode(
        claims,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> TokenClaims:
    """Decode and validate a JWT token.

    Args:
        token: JWT token string to decode.

    Returns:
        Validated token claims.

    Raises:
        HTTPException: If token is invalid or expired.
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        return TokenClaims(**payload)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> TokenClaims:
    """FastAPI dependency to get the current authenticated user.

    Args:
        credentials: Bearer token from request header.

    Returns:
        Validated token claims with user info and access scope.

    Raises:
        HTTPException: If credentials are missing or invalid.
    """
    return decode_token(credentials.credentials)


def require_repository_access(repository_id: str, claims: TokenClaims) -> None:
    """Verify user has access to a specific repository.

    Args:
        repository_id: Repository ID to check access for.
        claims: User's token claims.

    Raises:
        HTTPException: If user lacks access to the repository.
    """
    # Empty repository_ids means access to all repositories (admin/service token)
    if claims.repository_ids and repository_id not in claims.repository_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to repository {repository_id}",
        )


def get_branch_for_repository(repository_id: str, claims: TokenClaims) -> str | None:
    """Get the branch override for a repository from token claims.

    Args:
        repository_id: Repository ID to get branch for.
        claims: User's token claims.

    Returns:
        Branch name if override exists, None for default branch.
    """
    return claims.branch_overrides.get(repository_id)


# Type alias for dependency injection
CurrentUser = Annotated[TokenClaims, Depends(get_current_user)]
