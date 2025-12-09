"""Repository service for persistence and business logic."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from backend.src.config.logging import get_logger
from backend.src.config.settings import get_settings
from backend.src.db.session import get_session_context, get_sync_session_context
from backend.src.models.branch import Branch
from backend.src.models.notification import (
    Notification,
    NotificationSource,
    NotificationStatus,
)
from backend.src.models.repository import AccessState, AuthType, Repository
from backend.src.services.git.operations import GitCredentials

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

        async with get_session_context() as session:
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
            session.add(repository)
            await session.flush()

            # Create default branch tracking
            default_branch_record = Branch(
                id=uuid.uuid4(),
                repository_id=repository.id,
                name=default_branch,
                is_default=True,
            )
            session.add(default_branch_record)
            await session.flush()

            logger.info(
                "Repository created",
                repository_id=str(repository.id),
                branch_id=str(default_branch_record.id),
            )

            # Store IDs before session closes
            repo_id = str(repository.id)
            branch_id = str(default_branch_record.id)

        # Trigger initial ingestion for the new repository (outside the session)
        from backend.src.workers.tasks.ingestion import full_reindex_repository

        full_reindex_repository.delay(
            repository_id=repo_id,
            branch_id=branch_id,
        )

        logger.info(
            "Queued initial ingestion",
            repository_id=repo_id,
            branch_id=branch_id,
        )

        # Re-fetch repository to return fresh instance
        return await self.get_repository(uuid.UUID(repo_id))  # type: ignore

    async def get_repository(self, repository_id: uuid.UUID) -> Repository | None:
        """Get repository by ID.

        Args:
            repository_id: Repository UUID.

        Returns:
            Repository if found, None otherwise.
        """
        logger.debug("Fetching repository", repository_id=str(repository_id))

        async with get_session_context() as session:
            result = await session.execute(
                select(Repository)
                .options(selectinload(Repository.branches))
                .where(Repository.id == repository_id)
            )
            return result.scalar_one_or_none()

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

        async with get_session_context() as session:
            query = select(Repository).options(selectinload(Repository.branches))

            if repository_ids:
                uuid_list = [uuid.UUID(rid) for rid in repository_ids]
                query = query.where(Repository.id.in_(uuid_list))

            result = await session.execute(query)
            repositories = result.scalars().all()

            return [
                {
                    "id": str(repo.id),
                    "name": repo.name,
                    "default_branch": repo.default_branch,
                    "freshness_status": (
                        repo.branches[0].freshness_status.value
                        if repo.branches
                        else "pending"
                    ),
                    "last_indexed_at": (
                        repo.branches[0].last_indexed_at.isoformat()
                        if repo.branches and repo.branches[0].last_indexed_at
                        else None
                    ),
                    "backlog_size": (
                        repo.branches[0].backlog_size if repo.branches else 0
                    ),
                    "branches": [
                        {
                            "id": str(b.id),
                            "name": b.name,
                            "is_default": b.is_default,
                            "freshness_status": b.freshness_status.value,
                            "last_indexed_at": (
                                b.last_indexed_at.isoformat()
                                if b.last_indexed_at
                                else None
                            ),
                        }
                        for b in repo.branches
                    ],
                }
                for repo in repositories
            ]

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

        async with get_session_context() as session:
            await session.execute(
                update(Repository)
                .where(Repository.id == repository_id)
                .values(access_state=state, updated_at=datetime.now(timezone.utc))
            )

    async def get_branch(self, branch_id: uuid.UUID) -> Branch | None:
        """Get branch by ID.

        Args:
            branch_id: Branch UUID.

        Returns:
            Branch if found, None otherwise.
        """
        logger.debug("Fetching branch", branch_id=str(branch_id))

        async with get_session_context() as session:
            result = await session.execute(select(Branch).where(Branch.id == branch_id))
            return result.scalar_one_or_none()

    def get_git_credentials(self, repository: Repository) -> GitCredentials:
        """Build git credentials for a repository.

        Args:
            repository: Repository to get credentials for.

        Returns:
            GitCredentials instance configured for the repository.
        """
        settings = get_settings()

        # Handle different auth types
        if repository.auth_type == AuthType.NONE:
            return GitCredentials(auth_type=AuthType.NONE)

        if repository.auth_type == AuthType.TOKEN:
            # Priority: repository-specific credential > global provider token
            token = None
            if repository.auth_credential_ref:
                # In a real implementation, fetch from secrets manager
                # token = await secrets_manager.get_secret(repository.auth_credential_ref)
                logger.debug(
                    "Using repository-specific token",
                    repository_id=str(repository.id),
                )
            elif settings.git_provider_token:
                token = settings.git_provider_token.get_secret_value()
                logger.debug(
                    "Using global git provider token",
                    repository_id=str(repository.id),
                )

            return GitCredentials(
                auth_type=AuthType.TOKEN,
                token=token,
            )

        if repository.auth_type == AuthType.SSH_KEY:
            # In a real implementation, get SSH key path from secrets manager
            ssh_key_path = None
            if repository.auth_credential_ref:
                # ssh_key_path = await secrets_manager.get_ssh_key_path(
                #     repository.auth_credential_ref
                # )
                pass

            return GitCredentials(
                auth_type=AuthType.SSH_KEY,
                ssh_key_path=ssh_key_path,
            )

        # Default to no auth
        return GitCredentials(auth_type=AuthType.NONE)

    # =========================================================================
    # Synchronous methods for Celery workers
    # =========================================================================

    def get_repository_sync(self, repository_id: uuid.UUID) -> Repository | None:
        """Get repository by ID (synchronous version for workers).

        Args:
            repository_id: Repository UUID.

        Returns:
            Repository if found, None otherwise.
        """
        logger.debug("Fetching repository (sync)", repository_id=str(repository_id))

        with get_sync_session_context() as session:
            result = session.execute(
                select(Repository)
                .options(selectinload(Repository.branches))
                .where(Repository.id == repository_id)
            )
            return result.scalar_one_or_none()

    def get_branch_sync(self, branch_id: uuid.UUID) -> Branch | None:
        """Get branch by ID (synchronous version for workers).

        Args:
            branch_id: Branch UUID.

        Returns:
            Branch if found, None otherwise.
        """
        logger.debug("Fetching branch (sync)", branch_id=str(branch_id))

        with get_sync_session_context() as session:
            result = session.execute(select(Branch).where(Branch.id == branch_id))
            return result.scalar_one_or_none()


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

        async with get_session_context() as session:
            # Check for duplicate event_id (idempotency)
            if event_id:
                existing = await self._find_by_event_id(
                    session, repository_id, event_id
                )
                if existing:
                    logger.info(
                        "Duplicate notification ignored",
                        event_id=event_id,
                        existing_id=str(existing.id),
                    )
                    return existing

            # Get or create branch if branch_name is provided
            branch_id = None
            if branch_name:
                branch = await self._get_or_create_branch(
                    session, repository_id, branch_name
                )
                branch_id = branch.id

            notification = Notification(
                id=uuid.uuid4(),
                repository_id=repository_id,
                branch_id=branch_id,
                source=source,
                event_id=event_id,
                commit_sha=commit_sha,
                status=NotificationStatus.PENDING,
                received_at=datetime.now(timezone.utc),
            )
            session.add(notification)
            await session.flush()

            logger.info(
                "Notification created",
                notification_id=str(notification.id),
                repository_id=str(repository_id),
            )

            return notification

    async def _find_by_event_id(
        self,
        session,
        repository_id: uuid.UUID,
        event_id: str,
    ) -> Notification | None:
        """Find notification by event_id for idempotency check.

        Args:
            session: Database session.
            repository_id: Repository UUID.
            event_id: External event ID.

        Returns:
            Existing notification if found.
        """
        result = await session.execute(
            select(Notification)
            .where(Notification.repository_id == repository_id)
            .where(Notification.event_id == event_id)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_branch(
        self,
        session,
        repository_id: uuid.UUID,
        branch_name: str,
    ) -> Branch:
        """Get or create a branch record.

        Args:
            session: Database session.
            repository_id: Repository UUID.
            branch_name: Branch name.

        Returns:
            Branch record.
        """
        result = await session.execute(
            select(Branch)
            .where(Branch.repository_id == repository_id)
            .where(Branch.name == branch_name)
        )
        branch = result.scalar_one_or_none()

        if branch is None:
            branch = Branch(
                id=uuid.uuid4(),
                repository_id=repository_id,
                name=branch_name,
                is_default=False,
            )
            session.add(branch)
            await session.flush()

        return branch

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

        async with get_session_context() as session:
            await session.execute(
                update(Notification)
                .where(Notification.id == notification_id)
                .values(
                    status=status,
                    processed_at=processed_at,
                    error_message=error_message,
                )
            )

    async def get_pending_count(self, repository_id: uuid.UUID) -> int:
        """Get count of pending notifications for a repository.

        Args:
            repository_id: Repository UUID.

        Returns:
            Number of pending notifications.
        """
        from sqlalchemy import func

        async with get_session_context() as session:
            result = await session.execute(
                select(func.count())
                .select_from(Notification)
                .where(Notification.repository_id == repository_id)
                .where(Notification.status == NotificationStatus.PENDING)
            )
            return result.scalar_one()

    async def get_notification(
        self,
        notification_id: uuid.UUID,
    ) -> Notification | None:
        """Get notification by ID with related repository and branch info.

        Args:
            notification_id: Notification UUID.

        Returns:
            Notification if found, None otherwise.
        """
        logger.debug("Fetching notification", notification_id=str(notification_id))

        async with get_session_context() as session:
            result = await session.execute(
                select(Notification)
                .options(
                    selectinload(Notification.repository),
                    selectinload(Notification.branch),
                )
                .where(Notification.id == notification_id)
            )
            return result.scalar_one_or_none()


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
