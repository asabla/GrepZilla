# Implementation Plan: Code-Aware Search and Q&A

**Branch**: `001-code-search-index` | **Date**: Tue Dec 09 2025 | **Spec**: /Users/asabla/code/private/GrepZilla/specs/001-code-search-index/spec.md
**Input**: Feature specification from `/specs/001-code-search-index/spec.md`

**Note**: Filled per /speckit.plan workflow. Stop after Phase 2 planning.

## Summary

Backend service for code/documentation search and Q&A: ingest repos, chunk+embed with Chonkie, index into Meilisearch (full-text + vector) with citations by path and line. Keep indexes fresh via webhooks and scheduled re-index; expose HTTP API plus background workers with per-repo access control.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI + Uvicorn, Celery with Redis broker, Meilisearch v1.3+, Chonkie, Git provider SDK/webhooks  
**Storage**: PostgreSQL for metadata; Meilisearch (documents+embeddings)  
**Testing**: pytest + httpx + respx; OpenAPI contract validation  
**Target Platform**: Containers (Docker/K8s), Linux servers  
**Project Type**: Backend service + workers (no frontend)  
**Performance Goals**: p95 query <3s default branch; 90% notifications → index <10m; scheduled reindex within 24h; backlog alert >100 jobs  
**Constraints**: File parse limit 25MB; larger files cataloged only  
**Scale/Scope**: Up to 50 repos; ≤5GB per repo

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Quality gates: Acceptance tests per stories (middleware Q&A with citations; ingestion freshness; listing status). Test stack: pytest + httpx/respx; contract validation via OpenAPI; coverage target TBD in implementation.
- UX consistency: API responses include citations, timestamps, error reasons; access control enforced on listings and answers.
- Performance targets: p95 query <3s default branch; 90% notifications → index <10m; scheduled reindex within 24h; backlog alert >100 jobs.
- Risks: File size >25MB catalog-only; scale up to 50 repos (≤5GB each); monitor Meilisearch/postgres capacity.

## Project Structure

### Documentation (this feature)

```text
specs/001-code-search-index/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── models/
│   ├── services/
│   ├── api/
│   └── workers/
└── tests/
```

**Structure Decision**: Backend service + workers; single backend project with API + worker services and shared models/services. Tests grouped under backend/tests (contract/integration/unit).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
