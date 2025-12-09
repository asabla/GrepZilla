"""IndexRecord model for storing chunked and embedded content."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Float

from backend.src.db.base import Base


class IndexRecord(Base):
    """IndexRecord model representing a chunk of indexed content."""

    __tablename__ = "index_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
    chunk_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    embedding_vector: Mapped[list[float] | None] = mapped_column(
        ARRAY(Float),
        nullable=True,
    )
    line_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    line_end: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    language: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    artifact: Mapped["Artifact"] = relationship(
        "Artifact",
        back_populates="index_records",
    )
    repository: Mapped["Repository"] = relationship(
        "Repository",
    )
    branch: Mapped["Branch"] = relationship(
        "Branch",
        back_populates="index_records",
    )

    def __repr__(self) -> str:
        return f"<IndexRecord(id={self.id}, chunk_id={self.chunk_id})>"


# Import for type hints - avoid circular imports
from backend.src.models.artifact import Artifact  # noqa: E402, F401
from backend.src.models.branch import Branch  # noqa: E402, F401
from backend.src.models.repository import Repository  # noqa: E402, F401
