"""Repository request/response schemas."""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.src.models.repository import AccessState, AuthType


class RepositoryCreate(BaseModel):
    """Request schema for creating a repository."""

    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
            description="Repository display name",
        ),
    ]
    git_url: Annotated[
        str,
        Field(
            description="Git repository URL (HTTPS or SSH)",
        ),
    ]
    default_branch: Annotated[
        str,
        Field(
            default="main",
            max_length=255,
            description="Default branch to index",
        ),
    ]
    auth_type: Annotated[
        AuthType,
        Field(
            default=AuthType.NONE,
            description="Authentication type for repository access",
        ),
    ]
    credential_ref: Annotated[
        str | None,
        Field(
            default=None,
            max_length=512,
            description="Reference to credential in secrets manager",
        ),
    ]

    @field_validator("git_url")
    @classmethod
    def validate_git_url(cls, v: str) -> str:
        """Validate git URL format."""
        # Accept HTTPS URLs
        https_pattern = r"^https?://[^\s/$.?#].[^\s]*\.git$"
        # Accept SSH URLs
        ssh_pattern = r"^git@[^\s:]+:[^\s]+\.git$"
        # Accept generic git:// URLs
        git_pattern = r"^git://[^\s/$.?#].[^\s]*$"

        if not (
            re.match(https_pattern, v)
            or re.match(ssh_pattern, v)
            or re.match(git_pattern, v)
            or v.endswith(".git")  # Allow flexibility for valid URLs
        ):
            raise ValueError("Invalid git URL format")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate repository name."""
        if not v.strip():
            raise ValueError("Name cannot be empty or whitespace only")
        return v.strip()


class RepositoryResponse(BaseModel):
    """Response schema for a repository."""

    id: str = Field(description="Repository UUID")
    name: str = Field(description="Repository display name")
    git_url: str = Field(description="Git repository URL")
    default_branch: str = Field(description="Default branch")
    auth_type: AuthType = Field(description="Authentication type")
    access_state: AccessState = Field(description="Current access state")
    created_at: str = Field(description="Creation timestamp (ISO 8601)")
    updated_at: str = Field(description="Last update timestamp (ISO 8601)")

    model_config = ConfigDict(from_attributes=True)


class RepositoryListItem(BaseModel):
    """Repository item in listing response."""

    id: str = Field(description="Repository UUID")
    name: str = Field(description="Repository display name")
    default_branch: str = Field(description="Default branch")
    freshness_status: str = Field(description="Overall freshness status")
    last_indexed_at: str | None = Field(description="Last index timestamp")
    backlog_size: int = Field(description="Number of pending notifications")
    branches: list["BranchListItem"] = Field(default_factory=list)


class BranchListItem(BaseModel):
    """Branch item in repository listing."""

    name: str = Field(description="Branch name")
    is_default: bool = Field(description="Whether this is the default branch")
    freshness_status: str = Field(description="Branch freshness status")
    last_indexed_at: str | None = Field(description="Last index timestamp")
    backlog_size: int = Field(description="Pending notifications for branch")


class WebhookPayload(BaseModel):
    """Webhook notification payload."""

    event_id: str | None = Field(
        default=None,
        description="External event ID for idempotency",
    )
    branch: str | None = Field(
        default=None,
        description="Branch that was updated",
    )
    commit: str | None = Field(
        default=None,
        max_length=64,
        description="Commit SHA that triggered the event",
    )


class WebhookResponse(BaseModel):
    """Response for webhook intake."""

    notification_id: str = Field(description="Created notification UUID")
    repository_id: str = Field(description="Repository UUID")
    status: str = Field(
        default="accepted",
        description="Notification status",
    )
