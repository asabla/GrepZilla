"""Webhook routes for receiving repository change notifications."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from backend.src.api.deps.auth import CurrentUser, require_repository_access
from backend.src.api.schemas.repository import WebhookPayload, WebhookResponse
from backend.src.config.logging import get_logger
from backend.src.models.notification import NotificationSource
from backend.src.services.repository_service import get_notification_service

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/{repository_id}/webhooks",
    response_model=WebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive change notification",
    responses={
        202: {"description": "Notification accepted for processing"},
        401: {"description": "Missing or invalid credentials"},
        403: {"description": "Access denied to repository"},
        404: {"description": "Repository not found"},
        422: {"description": "Invalid repository ID format"},
    },
)
async def receive_webhook(
    repository_id: str,
    payload: WebhookPayload,
    current_user: CurrentUser,
) -> WebhookResponse:
    """Receive a webhook notification for repository changes.

    Accepts notifications from Git providers about repository changes.
    The notification is queued for asynchronous processing by the
    ingestion pipeline.

    Notifications with the same event_id are idempotent - duplicate
    submissions will return the existing notification without
    re-processing.

    Args:
        repository_id: Repository UUID.
        payload: Webhook notification payload.
        current_user: Authenticated user from JWT.

    Returns:
        Notification acceptance confirmation with notification ID.

    Raises:
        HTTPException: If repository not found or access denied.
    """
    logger.info(
        "Received webhook notification",
        repository_id=repository_id,
        event_id=payload.event_id,
        branch=payload.branch,
        user=current_user.sub,
    )

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

    # Create notification
    service = get_notification_service()

    try:
        notification = await service.create_notification(
            repository_id=repo_uuid,
            source=NotificationSource.WEBHOOK,
            event_id=payload.event_id,
            branch_name=payload.branch,
            commit_sha=payload.commit,
        )

        # Enqueue ingestion task
        from backend.src.workers.tasks.ingestion import process_notification

        process_notification.delay(str(notification.id))

        logger.info(
            "Webhook notification created",
            notification_id=str(notification.id),
            repository_id=repository_id,
            event_id=payload.event_id,
        )

        return WebhookResponse(
            notification_id=str(notification.id),
            repository_id=repository_id,
            status="accepted",
        )

    except Exception as e:
        logger.error(
            "Failed to create notification",
            repository_id=repository_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process notification",
        ) from e


@router.post(
    "/{repository_id}/refresh",
    response_model=WebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger manual repository refresh",
    responses={
        202: {"description": "Refresh triggered"},
        401: {"description": "Missing or invalid credentials"},
        403: {"description": "Access denied to repository"},
        404: {"description": "Repository not found"},
    },
)
async def trigger_refresh(
    repository_id: str,
    current_user: CurrentUser,
) -> WebhookResponse:
    """Manually trigger a repository refresh.

    Creates a MANUAL notification to trigger re-indexing of the
    repository. Useful for forcing a refresh outside of the
    normal webhook or scheduled re-indexing flow.

    Args:
        repository_id: Repository UUID.
        current_user: Authenticated user from JWT.

    Returns:
        Notification acceptance confirmation.
    """
    logger.info(
        "Manual refresh triggered",
        repository_id=repository_id,
        user=current_user.sub,
    )

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

    # Create manual notification
    service = get_notification_service()

    notification = await service.create_notification(
        repository_id=repo_uuid,
        source=NotificationSource.MANUAL,
    )

    # Enqueue ingestion task
    from backend.src.workers.tasks.ingestion import process_notification

    process_notification.delay(str(notification.id))

    logger.info(
        "Manual refresh notification created",
        notification_id=str(notification.id),
        repository_id=repository_id,
    )

    return WebhookResponse(
        notification_id=str(notification.id),
        repository_id=repository_id,
        status="accepted",
    )
