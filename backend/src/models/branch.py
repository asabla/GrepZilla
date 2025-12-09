"""Branch model for tracking repository branches."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.db.base import Base


class FreshnessStatus(StrEnum):
    """Index freshness status for a branch."""

    FRESH = "fresh"
    STALE = "stale"
    ERROR = "error"
    PENDING = "pending"


class Branch(Base):
    """Branch model representing a Git branch within a repository."""

    __tablename__ = "branches"

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
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    tracked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    last_indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_notification_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    freshness_status: Mapped[FreshnessStatus] = mapped_column(
        Enum(FreshnessStatus),
        nullable=False,
        default=FreshnessStatus.PENDING,
    )
    backlog_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="branches",
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        "Artifact",
        back_populates="branch",
        cascade="all, delete-orphan",
    )
    index_records: Mapped[list["IndexRecord"]] = relationship(
        "IndexRecord",
        back_populates="branch",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification",
        back_populates="branch",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Branch(id={self.id}, name={self.name}, repo_id={self.repository_id})>"


# Import for type hints - avoid circular imports
from backend.src.models.artifact import Artifact  # noqa: E402, F401
from backend.src.models.index_record import IndexRecord  # noqa: E402, F401
from backend.src.models.notification import Notification  # noqa: E402, F401
from backend.src.models.repository import Repository  # noqa: E402, F401
