"""Artifact model for tracking files in repositories."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.db.base import Base


class FileType(StrEnum):
    """Type classification for files."""

    CODE = "code"
    CONFIG = "config"
    DOC = "doc"
    PDF = "pdf"
    BINARY = "binary"
    OTHER = "other"


class ParseStatus(StrEnum):
    """Parsing status for artifacts."""

    PARSED = "parsed"
    SKIPPED = "skipped"
    FAILED = "failed"


class Artifact(Base):
    """Artifact model representing a file within a repository branch."""

    __tablename__ = "artifacts"

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
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    file_type: Mapped[FileType] = mapped_column(
        Enum(FileType),
        nullable=False,
        default=FileType.OTHER,
    )
    size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    parse_status: Mapped[ParseStatus] = mapped_column(
        Enum(ParseStatus),
        nullable=False,
        default=ParseStatus.SKIPPED,
    )
    has_line_map: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    last_seen_commit: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    last_indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
        back_populates="artifacts",
    )
    branch: Mapped["Branch"] = relationship(
        "Branch",
        back_populates="artifacts",
    )
    index_records: Mapped[list["IndexRecord"]] = relationship(
        "IndexRecord",
        back_populates="artifact",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Artifact(id={self.id}, path={self.path})>"


# Import for type hints - avoid circular imports
from backend.src.models.branch import Branch  # noqa: E402, F401
from backend.src.models.index_record import IndexRecord  # noqa: E402, F401
from backend.src.models.repository import Repository  # noqa: E402, F401
