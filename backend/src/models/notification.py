"""Notification model for webhook and scheduled events."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.db.base import Base

if TYPE_CHECKING:
    from backend.src.models.branch import Branch
    from backend.src.models.repository import Repository


class NotificationSource(StrEnum):
    """Source of the notification."""

    WEBHOOK = "webhook"
    SCHEDULE = "schedule"
    MANUAL = "manual"


class NotificationStatus(StrEnum):
    """Processing status of the notification."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


class Notification(Base):
    """Notification model representing webhook or scheduled ingestion events."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source: Mapped[NotificationSource] = mapped_column(
        Enum(NotificationSource),
        nullable=False,
    )
    event_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="External event ID from webhook provider",
    )
    commit_sha: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus),
        nullable=False,
        default=NotificationStatus.PENDING,
    )
    error_message: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="notifications",
    )
    branch: Mapped["Branch | None"] = relationship(
        "Branch",
        back_populates="notifications",
    )

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, source={self.source}, status={self.status})>"
