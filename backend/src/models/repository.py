"""Repository model for storing connected repositories."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.db.base import Base


class AuthType(StrEnum):
    """Authentication type for Git provider access."""

    NONE = "none"
    TOKEN = "token"
    SSH_KEY = "ssh_key"
    OAUTH = "oauth"


class AccessState(StrEnum):
    """Repository access state."""

    PENDING = "pending"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


class Repository(Base):
    """Repository model representing a connected Git repository."""

    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    git_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    default_branch: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="main",
    )
    auth_type: Mapped[AuthType] = mapped_column(
        Enum(AuthType),
        nullable=False,
        default=AuthType.NONE,
    )
    auth_credential_ref: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    access_state: Mapped[AccessState] = mapped_column(
        Enum(AccessState),
        nullable=False,
        default=AccessState.PENDING,
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
    branches: Mapped[list["Branch"]] = relationship(
        "Branch",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        "Artifact",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    queries: Mapped[list["Query"]] = relationship(
        "Query",
        back_populates="repositories",
        secondary="query_repositories",
    )

    def __repr__(self) -> str:
        return f"<Repository(id={self.id}, name={self.name})>"


# Import for type hints - avoid circular imports
from backend.src.models.artifact import Artifact  # noqa: E402, F401
from backend.src.models.branch import Branch  # noqa: E402, F401
from backend.src.models.notification import Notification  # noqa: E402, F401
from backend.src.models.query import Query  # noqa: E402, F401
