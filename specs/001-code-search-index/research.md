# Research

## Unknowns to Resolve
- Language/runtime selection for backend + workers
- HTTP framework choice and testing stack
- Performance budgets (query p95, ingest freshness, backlog thresholds)
- Scale assumptions (repo count, size thresholds)
- Access control integration patterns for per-repo permissions

## Findings

### Decision: Language/runtime: Python 3.11+
- Rationale: Rich ecosystem for HTTP (FastAPI), background workers (Celery/RQ), and strong SDK support for Git providers; aligns with Meilisearch/Chonkie clients.
- Alternatives considered: Go 1.22+ (simplicity/concurrency), TypeScript/Node (ecosystem). Python chosen for faster iteration and library maturity.

### Decision: HTTP framework: FastAPI + Uvicorn
- Rationale: Async-friendly, OpenAPI-first, good dependency injection/testing support, strong community.
- Alternatives considered: Flask (less async), Django (heavier), Go Fiber (requires Go stack).

### Decision: Worker stack: Celery (Redis broker) or Dramatiq
- Rationale: Mature task queue, ETA/retries, schedule integration for re-index; ecosystem fit with FastAPI.
- Alternatives: RQ (simpler, fewer features), Go workers (if Go chosen).

### Decision: Testing: pytest + httpx + respx + contract tests via OpenAPI schema validation
- Rationale: Standard Python testing stack, async support, schema validation for API contracts.
- Alternatives: unittest, Go testing if Go stack selected.

### Decision: Performance budgets
- Rationale: Align with success criteria; set targets: query p95 <3s for default-branch scope; ingest freshness 90% <10m post-notification; scheduled re-index within configured window; backlog size alerts if jobs > threshold.
- Alternatives: Stricter SLOs deferred pending load tests.

### Decision: Scale assumptions
- Rationale: Start with 50 active repos, repos up to 5GB each, binary exclusions; adjust after load tests.
- Alternatives: Higher scale requires sharding Meilisearch/postgres; out of scope for initial cut.

### Decision: Access control integration
- Rationale: Token-based auth in gateway; per-repo ACL stored in Postgres; enforce on queries and listings; Meilisearch filtered by repo/branch plus caller claims.
- Alternatives: Pass-through provider auth on each query (higher latency, complexity).

## Notes
- If Go stack preferred, mirror decisions with Fiber/Chi + Go workers; update tests to `go test` and use `testify`.
