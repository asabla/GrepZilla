"""Services package for GrepZilla backend.

This package contains all business logic services:

- query_service: Query processing with search, rerank, and citation assembly
- repository_service: Repository and notification management
- listing_service: Repository/branch listing with freshness status
- access_control: Access control helpers for repo/branch claims

Subpackages:
- ingestion: File discovery, embedding, and index writing
- search: Meilisearch client, chunking, and search pipeline
- listing: Response serializers
- observability: Metrics and monitoring utilities
"""

from backend.src.services.access_control import (
    AccessContext,
    AccessControlService,
    get_access_control_service,
)
from backend.src.services.listing_service import (
    BranchInfo,
    FreshnessStatus,
    ListingService,
    RepositoryInfo,
    get_listing_service,
)
from backend.src.services.query_service import QueryService, get_query_service
from backend.src.services.repository_service import (
    NotificationService,
    RepositoryService,
    get_notification_service,
    get_repository_service,
)

__all__ = [
    # Query service
    "QueryService",
    "get_query_service",
    # Repository service
    "RepositoryService",
    "NotificationService",
    "get_repository_service",
    "get_notification_service",
    # Listing service
    "ListingService",
    "BranchInfo",
    "RepositoryInfo",
    "FreshnessStatus",
    "get_listing_service",
    # Access control
    "AccessControlService",
    "AccessContext",
    "get_access_control_service",
]
