"""Repository routes for creating and listing repositories."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from backend.src.api.deps.auth import CurrentUser, require_repository_access
from backend.src.api.schemas.repository import (
    RepositoryCreate,
    RepositoryListItem,
    RepositoryResponse,
)
from backend.src.config.logging import get_logger
from backend.src.services.repository_service import get_repository_service

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Connect a repository for ingestion",
    responses={
        201: {"description": "Repository created successfully"},
        401: {"description": "Missing or invalid credentials"},
        403: {"description": "Access denied"},
        422: {"description": "Validation error"},
    },
)
async def create_repository(
    payload: RepositoryCreate,
    current_user: CurrentUser,
) -> RepositoryResponse:
    """Create a new repository for indexing.

    Creates a repository record and schedules initial ingestion.
    The repository will be in PENDING state until the first successful
    ingestion completes.

    Args:
        payload: Repository creation details.
        current_user: Authenticated user from JWT.

    Returns:
        Created repository with ID and status.
    """
    logger.info(
        "Creating repository",
        user=current_user.sub,
        name=payload.name,
        git_url=payload.git_url,
    )

    service = get_repository_service()

    try:
        repository = await service.create_repository(
            name=payload.name,
            git_url=payload.git_url,
            default_branch=payload.default_branch,
            auth_type=payload.auth_type,
            credential_ref=payload.credential_ref,
        )

        logger.info(
            "Repository created successfully",
            repository_id=str(repository.id),
            user=current_user.sub,
        )

        return RepositoryResponse(
            id=str(repository.id),
            name=repository.name,
            git_url=repository.git_url,
            default_branch=repository.default_branch,
            auth_type=repository.auth_type,
            access_state=repository.access_state,
            created_at=repository.created_at.isoformat(),
            updated_at=repository.updated_at.isoformat(),
        )

    except ValueError as e:
        logger.warning(
            "Repository creation failed",
            error=str(e),
            user=current_user.sub,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e


@router.get(
    "",
    response_model=list[RepositoryListItem],
    summary="List indexed repositories and branches",
    responses={
        200: {"description": "List of repositories with freshness status"},
        401: {"description": "Missing or invalid credentials"},
        403: {"description": "Access denied"},
    },
)
async def list_repositories(
    current_user: CurrentUser,
) -> list[RepositoryListItem]:
    """List repositories accessible to the current user.

    Returns repositories with freshness status, last indexed timestamp,
    and backlog size. Results are filtered based on the user's access
    claims in the JWT.

    Args:
        current_user: Authenticated user from JWT.

    Returns:
        List of repositories with branch status.
    """
    logger.debug(
        "Listing repositories",
        user=current_user.sub,
        repository_ids=current_user.repository_ids,
    )

    service = get_repository_service()

    # Filter by user's accessible repositories
    repository_ids = current_user.repository_ids if current_user.repository_ids else None

    repositories = await service.list_repositories(repository_ids=repository_ids)

    return [
        RepositoryListItem(
            id=repo.get("id", ""),
            name=repo.get("name", ""),
            default_branch=repo.get("default_branch", "main"),
            freshness_status=repo.get("freshness_status", "unknown"),
            last_indexed_at=repo.get("last_indexed_at"),
            backlog_size=repo.get("backlog_size", 0),
            branches=repo.get("branches", []),
        )
        for repo in repositories
    ]


@router.get(
    "/{repository_id}",
    response_model=RepositoryResponse,
    summary="Get repository details",
    responses={
        200: {"description": "Repository details"},
        401: {"description": "Missing or invalid credentials"},
        403: {"description": "Access denied"},
        404: {"description": "Repository not found"},
    },
)
async def get_repository(
    repository_id: str,
    current_user: CurrentUser,
) -> RepositoryResponse:
    """Get details for a specific repository.

    Args:
        repository_id: Repository UUID.
        current_user: Authenticated user from JWT.

    Returns:
        Repository details.

    Raises:
        HTTPException: If repository not found or access denied.
    """
    # Validate UUID format
    try:
        repo_uuid = uuid.UUID(repository_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid repository ID format",
        ) from e

    # Check access
    require_repository_access(repository_id, current_user)

    service = get_repository_service()
    repository = await service.get_repository(repo_uuid)

    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    return RepositoryResponse(
        id=str(repository.id),
        name=repository.name,
        git_url=repository.git_url,
        default_branch=repository.default_branch,
        auth_type=repository.auth_type,
        access_state=repository.access_state,
        created_at=repository.created_at.isoformat(),
        updated_at=repository.updated_at.isoformat(),
    )
