"""Repository service for persistence and business logic."""

import uuid
from datetime import datetime, timezone
from typing import Any

from backend.src.config.logging import get_logger
from backend.src.models.branch import Branch
from backend.src.models.notification import Notification, NotificationSource, NotificationStatus
from backend.src.models.repository import AccessState, AuthType, Repository

logger = get_logger(__name__)


class RepositoryService:
    """Service for repository management operations."""

    async def create_repository(
        self,
        name: str,
        git_url: str,
        default_branch: str = "main",
        auth_type: AuthType = AuthType.NONE,
        credential_ref: str | None = None,
    ) -> Repository:
        """Create a new repository.

        Args:
            name: Repository display name.
            git_url: Git repository URL.
            default_branch: Default branch to index.
            auth_type: Authentication type for access.
            credential_ref: Reference to stored credentials.

        Returns:
            Created Repository instance.
        """
        logger.info(
            "Creating repository",
            name=name,
            git_url=git_url,
            default_branch=default_branch,
        )

        now = datetime.now(timezone.utc)
        repository = Repository(
            id=uuid.uuid4(),
            name=name,
            git_url=git_url,
            default_branch=default_branch,
            auth_type=auth_type,
            auth_credential_ref=credential_ref,
            access_state=AccessState.PENDING,
            created_at=now,
            updated_at=now,
        )

        # In a real implementation, this would persist to database
        # async with session.begin():
        #     session.add(repository)
        #     await session.flush()

        # Create default branch tracking
        default_branch_record = Branch(
            id=uuid.uuid4(),
            repository_id=repository.id,
            name=default_branch,
            is_default=True,
        )

        logger.info(
            "Repository created",
            repository_id=str(repository.id),
            branch_id=str(default_branch_record.id),
        )

        return repository

    async def get_repository(self, repository_id: uuid.UUID) -> Repository | None:
        """Get repository by ID.

        Args:
            repository_id: Repository UUID.

        Returns:
            Repository if found, None otherwise.
        """
        logger.debug("Fetching repository", repository_id=str(repository_id))

        # In a real implementation, this would query the database
        # result = await session.execute(
        #     select(Repository).where(Repository.id == repository_id)
        # )
        # return result.scalar_one_or_none()

        return None

    async def list_repositories(
        self,
        repository_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List repositories with freshness status.

        Args:
            repository_ids: Optional list to filter by (for access control).

        Returns:
            List of repository info with freshness and backlog.
        """
        logger.debug("Listing repositories", filter_ids=repository_ids)

        # In a real implementation, this would query with aggregations
        # Placeholder return
        return []

    async def update_access_state(
        self,
        repository_id: uuid.UUID,
        state: AccessState,
    ) -> None:
        """Update repository access state.

        Args:
            repository_id: Repository UUID.
            state: New access state.
        """
        logger.info(
            "Updating repository access state",
            repository_id=str(repository_id),
            state=state,
        )

        # In a real implementation:
        # await session.execute(
        #     update(Repository)
        #     .where(Repository.id == repository_id)
        #     .values(access_state=state)
        # )


class NotificationService:
    """Service for notification/webhook handling."""

    async def create_notification(
        self,
        repository_id: uuid.UUID,
        source: NotificationSource = NotificationSource.WEBHOOK,
        event_id: str | None = None,
        branch_name: str | None = None,
        commit_sha: str | None = None,
    ) -> Notification:
        """Create a notification for ingestion.

        Args:
            repository_id: Repository UUID.
            source: Notification source type.
            event_id: External event ID for idempotency.
            branch_name: Branch that was updated.
            commit_sha: Commit SHA that triggered event.

        Returns:
            Created Notification instance.
        """
        logger.info(
            "Creating notification",
            repository_id=str(repository_id),
            source=source,
            event_id=event_id,
            branch=branch_name,
        )

        # Check for duplicate event_id (idempotency)
        if event_id:
            existing = await self._find_by_event_id(repository_id, event_id)
            if existing:
                logger.info(
                    "Duplicate notification ignored",
                    event_id=event_id,
                    existing_id=str(existing.id),
                )
                return existing

        notification = Notification(
            id=uuid.uuid4(),
            repository_id=repository_id,
            source=source,
            event_id=event_id,
            commit_sha=commit_sha,
            status=NotificationStatus.PENDING,
            received_at=datetime.now(timezone.utc),
        )

        # In a real implementation, persist and get branch_id
        # async with session.begin():
        #     if branch_name:
        #         branch = await self._get_or_create_branch(repository_id, branch_name)
        #         notification.branch_id = branch.id
        #     session.add(notification)

        logger.info(
            "Notification created",
            notification_id=str(notification.id),
            repository_id=str(repository_id),
        )

        return notification

    async def _find_by_event_id(
        self,
        repository_id: uuid.UUID,
        event_id: str,
    ) -> Notification | None:
        """Find notification by event_id for idempotency check.

        Args:
            repository_id: Repository UUID.
            event_id: External event ID.

        Returns:
            Existing notification if found.
        """
        # In a real implementation:
        # result = await session.execute(
        #     select(Notification)
        #     .where(Notification.repository_id == repository_id)
        #     .where(Notification.event_id == event_id)
        # )
        # return result.scalar_one_or_none()
        return None

    async def update_status(
        self,
        notification_id: uuid.UUID,
        status: NotificationStatus,
        error_message: str | None = None,
    ) -> None:
        """Update notification processing status.

        Args:
            notification_id: Notification UUID.
            status: New status.
            error_message: Error message if status is ERROR.
        """
        logger.info(
            "Updating notification status",
            notification_id=str(notification_id),
            status=status,
        )

        processed_at = None
        if status in (NotificationStatus.DONE, NotificationStatus.ERROR):
            processed_at = datetime.now(timezone.utc)

        # In a real implementation:
        # await session.execute(
        #     update(Notification)
        #     .where(Notification.id == notification_id)
        #     .values(
        #         status=status,
        #         processed_at=processed_at,
        #         error_message=error_message,
        #     )
        # )

    async def get_pending_count(self, repository_id: uuid.UUID) -> int:
        """Get count of pending notifications for a repository.

        Args:
            repository_id: Repository UUID.

        Returns:
            Number of pending notifications.
        """
        # In a real implementation:
        # result = await session.execute(
        #     select(func.count())
        #     .select_from(Notification)
        #     .where(Notification.repository_id == repository_id)
        #     .where(Notification.status == NotificationStatus.PENDING)
        # )
        # return result.scalar_one()
        return 0


# Service singletons
_repository_service: RepositoryService | None = None
_notification_service: NotificationService | None = None


def get_repository_service() -> RepositoryService:
    """Get repository service singleton."""
    global _repository_service
    if _repository_service is None:
        _repository_service = RepositoryService()
    return _repository_service


def get_notification_service() -> NotificationService:
    """Get notification service singleton."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
