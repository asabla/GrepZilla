"""Response serializers for repository/branch listing."""

from datetime import datetime

from backend.src.api.schemas.repository import BranchListItem, RepositoryListItem
from backend.src.services.listing_service import BranchInfo, RepositoryInfo


def serialize_branch(branch: BranchInfo) -> BranchListItem:
    """Serialize branch info to API response format.

    Args:
        branch: Branch info from listing service.

    Returns:
        BranchListItem for API response.
    """
    return BranchListItem(
        name=branch.name,
        is_default=branch.is_default,
        freshness_status=branch.freshness_status.value,
        last_indexed_at=_format_datetime(branch.last_indexed_at),
        backlog_size=branch.backlog_size,
    )


def serialize_repository(repo: RepositoryInfo) -> RepositoryListItem:
    """Serialize repository info to API response format.

    Args:
        repo: Repository info from listing service.

    Returns:
        RepositoryListItem for API response.
    """
    return RepositoryListItem(
        id=repo.id,
        name=repo.name,
        default_branch=repo.default_branch,
        freshness_status=repo.freshness_status.value,
        last_indexed_at=_format_datetime(repo.last_indexed_at),
        backlog_size=repo.backlog_size,
        branches=[serialize_branch(b) for b in repo.branches],
    )


def serialize_repositories(
    repos: list[RepositoryInfo],
) -> list[RepositoryListItem]:
    """Serialize list of repositories to API response format.

    Args:
        repos: List of repository infos from listing service.

    Returns:
        List of RepositoryListItem for API response.
    """
    return [serialize_repository(repo) for repo in repos]


def _format_datetime(dt: datetime | None) -> str | None:
    """Format datetime to ISO 8601 string.

    Args:
        dt: Datetime to format.

    Returns:
        ISO 8601 string or None.
    """
    if dt is None:
        return None
    return dt.isoformat()
