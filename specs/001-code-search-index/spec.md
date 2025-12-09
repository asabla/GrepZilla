# Feature Specification: Code-Aware Search and Q&A

**Feature Branch**: `001-code-search-index`  
**Created**: Tue Dec 09 2025  
**Status**: Draft  
**Input**: User description: "Build a service that can index and understand software code repositories so that engineers can ask natural language questions about their code and configuration. The service continuously ingests one or many repositories, discovers all files (source code, configs, documentation, PDFs, images, and other common assets), and breaks them into searchable units while preserving file paths and line ranges. Users can ask questions like “where do we implement middlewares and how are these configured?” and get an answer that not only explains the behavior but also points to the exact files and line numbers across one or multiple repositories and branches. The system should keep repositories up to date over time via change notifications and scheduled re-indexing, allow users to list what is currently indexed, and prioritize default branches while still allowing queries against other branches when explicitly requested."

## Clarifications

### Session 2025-12-09
- Q: What authN/Z pattern should enforce per-repo and per-branch access? → A: Gateway-issued JWT with repo/branch claims enforced by API and workers (no per-request provider passthrough).
- Q: What performance budgets should we target for query latency, freshness, and backlog alerts? → A: p95 query <3s default-branch; 90% notifications → index <10m; scheduled reindex window 24h; backlog alert when >100 pending jobs.
- Q: Which stack should we use for API and workers? → A: Python 3.11, FastAPI + Uvicorn, Celery with Redis broker.
- Q: How should JWT claims encode repo/branch access? → A: Claims carry repos:[repo_id] and branches:{repo_id:[branch]} enforced by API and workers.
- Q: What scale and size limits apply to repositories and files? → A: Up to 50 repos, 5GB each; parse files ≤25MB, larger files cataloged only.
- Q: How should we observe freshness and backlog health? → A: Emit metrics for backlog size, notification→index latency, reindex duration; alert on thresholds; structured error logs per repo/branch.
- Q: How should branch selection behave by default? → A: Default to each repo’s default branch; honor explicit per-repo branch overrides when provided.
- Q: What chunking and embedding strategy should we use? → A: Chunk to ~800 tokens with ~10% overlap, language-aware parsing, embeddings via OpenAI-compatible API (single provider) with fallback option.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask about middleware behavior (Priority: P1)

An engineer asks a natural language question about middleware implementation and configuration across one or more repositories and receives an explanation with references to specific files and line ranges.

**Why this priority**: Directly delivers the core value of code understanding and answers real questions engineers have.

**Independent Test**: Submit a middleware-related question against indexed repos and verify the answer cites correct files and line ranges while explaining behavior.

**Acceptance Scenarios**:

1. **Given** repositories are indexed with default branches prioritized, **When** the engineer asks about middleware implementation, **Then** the response describes the behavior and cites file paths with line ranges from relevant repos.
2. **Given** a question that spans config and code, **When** the engineer requests clarification on configuration, **Then** the answer includes referenced config files with relevant line ranges.

---

### User Story 2 - Add and keep repositories fresh (Priority: P2)

A platform admin connects one or more repositories for continuous ingestion, enabling change notifications and scheduled re-indexing so indexes stay current.

**Why this priority**: Without fresh indexes, answers become stale and lose trust; ingestion reliability underpins the service.

**Independent Test**: Add a repository, trigger a change notification, and verify the index updates within the expected time window without manual intervention.

**Acceptance Scenarios**:

1. **Given** a repository is added with default branch set, **When** new commits arrive via change notification, **Then** the index updates to reflect changes within the agreed window.
2. **Given** scheduled re-indexing is configured, **When** no notifications arrive, **Then** the system still refreshes the index on schedule and surfaces any failures.

---

### User Story 3 - Discover indexed scope (Priority: P3)

An engineer lists what repositories and branches are indexed, sees their freshness and status, and can request queries against non-default branches explicitly.

**Why this priority**: Visibility builds confidence and allows targeted branch queries without guessing coverage.

**Independent Test**: List indexed repositories and branches, observe timestamps/status, and run a query against a non-default branch when explicitly requested.

**Acceptance Scenarios**:

1. **Given** multiple repositories are connected, **When** the engineer lists indexed items, **Then** they see repositories, tracked branches, freshness timestamps, and indexing status.
2. **Given** a non-default branch exists, **When** the engineer explicitly requests that branch in a query, **Then** results come from that branch with citations, while default branches remain prioritized otherwise.

---

### Edge Cases

- Repositories with restricted access or revoked credentials trigger failures; system reports the issue without exposing content.
- Large binary or unsupported file types are discovered; system records their presence but excludes them from text answers while keeping paths visible.
- Branch renames or deletions occur; system updates branch tracking and prevents stale references.
- Change notifications are missed; scheduled re-indexing backfills missed updates and reports if unable to reconcile.
- Deeply nested monorepos or many concurrent repos may slow ingestion; system queues work and surfaces backlog status.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST ingest one or many repositories (up to 50; ≤5GB each) and discover all file types (source, configs, docs, PDFs, images, common assets) for indexing.
- **FR-002**: System MUST split discovered content into searchable units while preserving original file paths and line ranges for citation; chunk size ~800 tokens with ~10% overlap; language-aware parsing where possible; files >25MB are cataloged without parsing.
- **FR-003**: System MUST prioritize default branches for indexing and querying while allowing explicit queries against non-default branches; default per repo unless caller specifies branches per repo.
- **FR-004**: System MUST support continuous updates via change notifications and fallback scheduled re-indexing to keep indexes current.
- **FR-005**: System MUST allow users to list indexed repositories, tracked branches, freshness timestamps, backlog size, and indexing status.
- **FR-006**: System MUST answer natural language questions with explanations and cite exact file paths and line ranges across repositories and branches, using each repository’s default branch unless an explicit per-repo branch override is provided.
- **FR-007**: System MUST handle files it cannot parse (e.g., binaries) by recording their presence and excluding them from text answers without failing ingestion.
- **FR-008**: System MUST respect repository access controls so that only authorized users can view indexed content and answers, enforced via gateway-issued JWT claims that list allowed repositories (repos:[repo_id]) and branch scopes (branches:{repo_id:[branch]}).
- **FR-009**: System MUST provide visibility into ingestion errors or stale indexes, including reason and time detected, via structured error logs (repo/branch) and metrics for backlog size, notification→index latency, and reindex duration with alerting on thresholds.

### Acceptance Criteria

- **FR-001**: Adding repositories discovers expected file types; unsupported items are cataloged without failure.
- **FR-002**: Search results reference correct file paths and line ranges that map back to source files.
- **FR-003**: Default branches are used unless a query explicitly names another branch, which is then used for that request.
- **FR-004**: Change notifications and scheduled re-indexing refresh indexes within defined freshness windows.
- **FR-005**: Listing indexed scope shows repositories, tracked branches, statuses, and timestamps visible to authorized users.
- **FR-006**: Q&A answers include explanations plus citations to files and line ranges used.
- **FR-007**: Binaries and unparseable files appear in inventory/path listings but never in textual answers.
- **FR-008**: Access to indexed content and answers is blocked for unauthorized users and logged as an access failure.
- **FR-009**: Ingestion or freshness issues surface with reason and detection time in status views or alerts.

### Key Entities *(include if feature involves data)*

- **Repository**: Source code host location with metadata (name, default branch, access state).
- **Branch**: Versioned line within a repository with freshness metadata and tracking status.
- **Artifact**: Discovered file or asset with path, type, size, and line-mapping availability.
- **Index Record**: Searchable unit derived from an artifact, linked to file path and line ranges.
- **Query**: Natural language request with scope (repositories/branches) and response containing explanations plus citations.
- **Notification**: Change event or scheduled trigger indicating repository updates.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 95% of questions about indexed content return answers with correct file-path and line-range citations validated against source files.
- **SC-002**: 90% of change notifications result in updated index availability within 10 minutes; scheduled re-index completes within its configured 24h window; backlog alert if pending jobs >100.
- **SC-003**: 95% of queries return within 3 seconds for default-branch scope on repositories up to agreed size thresholds; branch-specific queries respect stated priority while honoring explicit branch requests. p95 target set to <3s.
- **SC-004**: 100% of indexed content access follows repository permissions; unauthorized users receive no content and see clear access-error messaging. Enforcement validated via JWT claims filtering on repository IDs and branches per token (repos:[repo_id], branches:{repo_id:[branch]}).
- **SC-005**: Users can list indexed repositories and branches with freshness and status, with zero stale items older than the scheduled re-index interval unless flagged with a visible error state.

### Validation Notes

- SC-001 validated by comparing cited line ranges against current source snapshots.
- SC-002 validated by measuring time from notification to index availability, scheduled job completion times, and backlog size alerts.
- SC-003 validated by timing query responses across default and explicitly requested branches within size thresholds.
- SC-004 validated via permission checks ensuring unauthorized users receive access errors with no content exposure; claims include repos:[repo_id] and branches:{repo_id:[branch]}.
- SC-005 validated by listing indexed scope and confirming no stale entries beyond the scheduled interval unless flagged.

## Assumptions

- Default branch is treated as primary for indexing and query priority; other branches are only searched when explicitly requested.
- Standard repository authentication and authorization are available and enforced during ingestion and query access.
- Basic text extraction is available for common document types (e.g., Markdown, PDFs with text/OCR) while unparseable binaries are cataloged but not answerable.
- Change notifications are available where supported; otherwise, scheduled re-indexing covers missed updates.
- API and workers run on Python 3.11 using FastAPI + Uvicorn with Celery on Redis for background processing.
