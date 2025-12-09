"""Listing service for aggregating repositories/branches with freshness status."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from backend.src.config.constants import FRESHNESS_STALE_THRESHOLD_HOURS
from backend.src.config.logging import get_logger
from backend.src.models.repository import AccessState

logger = get_logger(__name__)


class FreshnessStatus(str, Enum):
    """Repository/branch freshness status."""

    FRESH = "fresh"
    STALE = "stale"
    INDEXING = "indexing"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class BranchInfo:
    """Branch information for listing response."""

    name: str
    is_default: bool
    freshness_status: FreshnessStatus
    last_indexed_at: datetime | None
    backlog_size: int


@dataclass
class RepositoryInfo:
    """Repository information for listing response."""

    id: str
    name: str
    default_branch: str
    freshness_status: FreshnessStatus
    last_indexed_at: datetime | None
    backlog_size: int
    branches: list[BranchInfo]


class ListingService:
    """Service for listing repositories and branches with status aggregation."""

    async def list_repositories(
        self,
        repository_ids: list[str] | None = None,
    ) -> list[RepositoryInfo]:
        """List repositories with freshness status and backlog.

        Args:
            repository_ids: Optional list to filter by (for access control).
                If None or empty, returns all repositories (admin mode).

        Returns:
            List of RepositoryInfo with aggregated branch status.
        """
        logger.debug(
            "Listing repositories with status",
            filter_ids=repository_ids,
        )

        # In a real implementation, this would query the database with
        # aggregations for freshness and backlog counts
        #
        # SELECT r.*, 
        #     COUNT(n.id) FILTER (WHERE n.status = 'pending') as backlog_size,
        #     MAX(b.last_indexed_at) as last_indexed_at
        # FROM repositories r
        # LEFT JOIN branches b ON b.repository_id = r.id
        # LEFT JOIN notifications n ON n.repository_id = r.id
        # WHERE (repository_ids IS NULL OR r.id IN :repository_ids)
        # GROUP BY r.id

        # Placeholder - in production, query and aggregate from database
        return []

    async def get_repository_with_branches(
        self,
        repository_id: uuid.UUID,
    ) -> RepositoryInfo | None:
        """Get single repository with all branches and status.

        Args:
            repository_id: Repository UUID.

        Returns:
            RepositoryInfo if found, None otherwise.
        """
        logger.debug(
            "Getting repository with branches",
            repository_id=str(repository_id),
        )

        # In a real implementation:
        # repo = await session.get(Repository, repository_id)
        # if not repo:
        #     return None
        #
        # branches = await self._get_branches_with_status(repository_id)
        # return self._build_repository_info(repo, branches)

        return None

    async def get_branch_status(
        self,
        repository_id: uuid.UUID,
        branch_name: str,
    ) -> BranchInfo | None:
        """Get status for a specific branch.

        Args:
            repository_id: Repository UUID.
            branch_name: Branch name.

        Returns:
            BranchInfo if found, None otherwise.
        """
        logger.debug(
            "Getting branch status",
            repository_id=str(repository_id),
            branch=branch_name,
        )

        # In a real implementation, query branch and aggregate status
        return None

    def compute_freshness_status(
        self,
        last_indexed_at: datetime | None,
        access_state: AccessState,
        pending_count: int,
    ) -> FreshnessStatus:
        """Compute freshness status based on timestamps and state.

        Args:
            last_indexed_at: Last successful index time.
            access_state: Current repository access state.
            pending_count: Number of pending notifications.

        Returns:
            Computed FreshnessStatus.
        """
        # Check for error state
        if access_state == AccessState.ERROR:
            return FreshnessStatus.ERROR

        # Check if currently indexing
        if pending_count > 0:
            return FreshnessStatus.INDEXING

        # Check if never indexed
        if last_indexed_at is None:
            return FreshnessStatus.UNKNOWN

        # Check staleness
        now = datetime.now(timezone.utc)
        hours_since_index = (now - last_indexed_at).total_seconds() / 3600

        if hours_since_index > FRESHNESS_STALE_THRESHOLD_HOURS:
            return FreshnessStatus.STALE

        return FreshnessStatus.FRESH

    def aggregate_repository_status(
        self,
        branches: list[BranchInfo],
    ) -> FreshnessStatus:
        """Aggregate branch statuses to repository-level status.

        Uses the "worst" status from all branches.

        Args:
            branches: List of branch infos with status.

        Returns:
            Aggregated FreshnessStatus.
        """
        if not branches:
            return FreshnessStatus.UNKNOWN

        # Priority order: ERROR > STALE > INDEXING > UNKNOWN > FRESH
        status_priority = {
            FreshnessStatus.ERROR: 0,
            FreshnessStatus.STALE: 1,
            FreshnessStatus.INDEXING: 2,
            FreshnessStatus.UNKNOWN: 3,
            FreshnessStatus.FRESH: 4,
        }

        worst_status = FreshnessStatus.FRESH
        for branch in branches:
            if status_priority[branch.freshness_status] < status_priority[worst_status]:
                worst_status = branch.freshness_status

        return worst_status


# Singleton instance
_listing_service: ListingService | None = None


def get_listing_service() -> ListingService:
    """Get listing service singleton.

    Returns:
        ListingService instance.
    """
    global _listing_service
    if _listing_service is None:
        _listing_service = ListingService()
    return _listing_service
