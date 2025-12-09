"""Query model for storing search query history."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Table, Column, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.db.base import Base

if TYPE_CHECKING:
    from backend.src.models.repository import Repository


# Association table for Query to Repository many-to-many relationship
query_repositories = Table(
    "query_repositories",
    Base.metadata,
    Column("query_id", UUID(as_uuid=True), ForeignKey("queries.id", ondelete="CASCADE"), primary_key=True),
    Column("repository_id", UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True),
)


class Query(Base):
    """Query model representing a search query and its response."""

    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    scope_branches: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Map of repository_id -> branch name for query scope",
    )
    query_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    response_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    response_citations: Mapped[list[dict] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Array of citation objects with path, line_start, line_end",
    )
    response_latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    repositories: Mapped[list["Repository"]] = relationship(
        "Repository",
        secondary=query_repositories,
        back_populates="queries",
    )

    def __repr__(self) -> str:
        return f"<Query(id={self.id}, text={self.query_text[:50]}...)>"
