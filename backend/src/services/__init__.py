"""Services package for GrepZilla backend.

This package contains all business logic services:

- query_service: Query processing with search, rerank, and citation assembly
- agent_query_service: Agentic query processing using OpenAI Agents SDK
- repository_service: Repository and notification management
- listing_service: Repository/branch listing with freshness status
- access_control: Access control helpers for repo/branch claims

Subpackages:
- ai: LLM, embeddings, and agent clients
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


# Lazy imports for heavy modules (OpenAI Agents SDK)
# This prevents Celery workers from loading these at fork time
def get_agent_query_service():
    """Get singleton agent query service instance (lazy import)."""
    from backend.src.services.agent_query_service import get_agent_query_service as _get

    return _get()


def get_AgentQueryService():
    """Get AgentQueryService class (lazy import)."""
    from backend.src.services.agent_query_service import AgentQueryService

    return AgentQueryService


__all__ = [
    # Query service
    "QueryService",
    "get_query_service",
    # Agent query service (lazy imports)
    "get_agent_query_service",
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
