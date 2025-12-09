---

description: "Task list for feature implementation"
---

# Tasks: Code-Aware Search and Q&A

**Input**: Design documents from `/specs/001-code-search-index/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Include required tests per constitution (unit, integration, contract) for each story; add any extra tests explicitly requested in the feature specification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create backend structure under `backend/src/` and `backend/tests/` per plan.md
- [ ] T002 Initialize Python project dependencies (FastAPI, Celery, Redis, Meilisearch, Chonkie, pytest/httpx/respx) in `pyproject.toml`
- [ ] T003 [P] Configure environment settings module for DB, Meilisearch, Redis, Git provider token in `backend/src/config/settings.py`
- [ ] T004 [P] Add logging/tracing configuration shared by API and workers in `backend/src/config/logging.py`
- [ ] T005 [P] Define constants for file size limits and performance budgets in `backend/src/config/constants.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 Setup migration framework and initial revision folder in `backend/src/db/migrations/`
- [ ] T007 [P] Create Repository model and schema (id, name, git_url, default_branch, auth fields) in `backend/src/models/repository.py`
- [ ] T008 [P] Create Branch model with tracking/freshness fields in `backend/src/models/branch.py`
- [ ] T009 [P] Create Artifact and IndexRecord models with parsing/line map fields in `backend/src/models/artifact.py` and `backend/src/models/index_record.py`
- [ ] T010 [P] Create Query and Notification models for history and events in `backend/src/models/query.py` and `backend/src/models/notification.py`
- [ ] T011 Implement DB session/engine configuration in `backend/src/db/session.py`
- [ ] T012 Implement JWT auth dependency enforcing repo/branch claims in `backend/src/api/deps/auth.py`
- [ ] T013 Wire FastAPI application factory and router registration in `backend/src/api/main.py`
- [ ] T014 [P] Configure Celery app with Redis broker and task autodiscovery in `backend/src/workers/app.py`
- [ ] T015 [P] Implement Meilisearch client setup and index bootstrap in `backend/src/services/search/index_client.py`
- [ ] T016 [P] Implement Chonkie-based chunking/embedding utility with token limits in `backend/src/services/search/chunk_embed.py`
- [ ] T017 Add structured error handling and response shape middleware in `backend/src/api/middleware/errors.py`
- [ ] T018 Add configuration-driven feature flags for branch overrides and size thresholds in `backend/src/config/feature_flags.py`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Ask about middleware behavior (Priority: P1) 🎯 MVP

**Goal**: Answer middleware questions with citations to file paths and line ranges across repositories/branches.

**Independent Test**: Submit a middleware-related question; response explains behavior and cites correct files/lines.

### Tests for User Story 1

- [ ] T019 [P] [US1] Add contract test for `POST /queries` happy/error paths in `backend/tests/contract/test_queries.py`
- [ ] T020 [P] [US1] Add integration test for middleware question with citations in `backend/tests/integration/test_queries_middleware.py`

### Implementation for User Story 1

- [ ] T021 [P] [US1] Define query request/response schemas with citations in `backend/src/api/schemas/query.py`
- [ ] T022 [P] [US1] Implement search pipeline with branch-aware filters in `backend/src/services/search/search_pipeline.py`
- [ ] T023 [P] [US1] Implement query service combining chunk retrieval, rerank, and citation assembly in `backend/src/services/query_service.py`
- [ ] T024 [P] [US1] Implement prompt/context builder for middleware-focused Q&A in `backend/src/services/search/prompt_builder.py`
- [ ] T025 [US1] Implement `POST /queries` route with auth and latency metrics in `backend/src/api/routes/queries.py`
- [ ] T026 [US1] Add request/response logging and timing instrumentation for queries in `backend/src/api/observability/query_metrics.py`

**Checkpoint**: User Story 1 fully functional and independently testable

---

## Phase 4: User Story 2 - Add and keep repositories fresh (Priority: P2)

**Goal**: Connect repositories, process notifications, and keep indexes fresh via webhooks and scheduled re-indexing.

**Independent Test**: Add a repository, send a change notification, and verify index refreshes within expected window automatically.

### Tests for User Story 2

- [ ] T027 [P] [US2] Add contract test for `POST /repositories` creation flow in `backend/tests/contract/test_repositories_post.py`
- [ ] T028 [P] [US2] Add contract test for `POST /repositories/{id}/webhooks` notification intake in `backend/tests/contract/test_webhooks_post.py`
- [ ] T029 [P] [US2] Add integration test for notification→ingestion→index update latency in `backend/tests/integration/test_ingestion_notifications.py`

### Implementation for User Story 2

- [ ] T030 [P] [US2] Implement repository creation handler with validation/auth in `backend/src/api/routes/repositories.py`
- [ ] T031 [P] [US2] Implement webhook intake handler enqueueing ingestion in `backend/src/api/routes/webhooks.py`
- [ ] T032 [US2] Implement repository service for persistence and default branch tracking in `backend/src/services/repository_service.py`
- [ ] T033 [P] [US2] Implement artifact discovery (respect size/type rules) in `backend/src/services/ingestion/discover.py`
- [ ] T034 [P] [US2] Implement chunk + embedding tasks using Chonkie in `backend/src/services/ingestion/embed.py`
- [ ] T035 [US2] Implement index writer to Meilisearch with citations in `backend/src/services/ingestion/index_writer.py`
- [ ] T036 [US2] Implement Celery tasks orchestrating notification ingestion in `backend/src/workers/tasks/ingestion.py`
- [ ] T037 [US2] Implement scheduled reindex task honoring freshness window in `backend/src/workers/tasks/schedule.py`
- [ ] T038 [P] [US2] Emit freshness/backlog metrics and alerts in `backend/src/services/observability/freshness_metrics.py`
- [ ] T039 [US2] Enforce >25MB catalog-only handling and binary skip rules in `backend/src/services/ingestion/file_filters.py`

**Checkpoint**: User Story 2 fully functional and independently testable

---

## Phase 5: User Story 3 - Discover indexed scope (Priority: P3)

**Goal**: List indexed repositories/branches with freshness/status and support explicit branch queries.

**Independent Test**: List repositories/branches with timestamps/status/backlog and run a query against a specified non-default branch.

### Tests for User Story 3

- [ ] T040 [P] [US3] Add contract test for `GET /repositories` listing scope/status in `backend/tests/contract/test_repositories_get.py`
- [ ] T041 [P] [US3] Add integration test for branch-override query path in `backend/tests/integration/test_branch_override_queries.py`

### Implementation for User Story 3

- [ ] T042 [P] [US3] Implement listing service aggregating branches/freshness/backlog in `backend/src/services/listing_service.py`
- [ ] T043 [US3] Add GET handler for repositories listing with access control in `backend/src/api/routes/repositories.py`
- [ ] T044 [P] [US3] Add repository/branch response schemas for listing output in `backend/src/api/schemas/repository.py`
- [ ] T045 [US3] Extend query service to honor per-repo branch overrides with default fallback in `backend/src/services/query_service.py`
- [ ] T046 [P] [US3] Implement access control helper applying repo/branch claims to queries in `backend/src/services/access_control.py`
- [ ] T047 [US3] Add response serializer for freshness/status/backlog fields in `backend/src/services/listing/serializers.py`

**Checkpoint**: All user stories independently functional

---

## Final Phase: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T048 [P] Update quickstart with env/command details validated in `specs/001-code-search-index/quickstart.md`
- [ ] T049 Run quickstart validation walkthrough and note gaps in `specs/001-code-search-index/quickstart.md`
- [ ] T050 [P] Add performance/alert thresholds (query p95, freshness, backlog) configuration in `backend/src/config/perf.py`
- [ ] T051 Code cleanup and log/metric consistency pass in `backend/src/`

---

## Dependencies & Execution Order

- Setup (Phase 1) → Foundational (Phase 2) → User Stories (Phases 3–5) → Polish (Final)
- User Story priority/order: US1 (P1) → US2 (P2) → US3 (P3); all depend on Foundational but can run in parallel if foundation complete and team available.
- Within each story: Tests (if present) before implementation; models → services → endpoints → observability.

## Parallel Opportunities (Examples)

- Phase 1: T003, T004, T005 can run in parallel after T002.
- Phase 2: T007–T010 model files can proceed in parallel; T014–T016 client/worker utilities can proceed in parallel.
- User Story 1: T019–T024 can run in parallel; T025 depends on prior tasks wiring.
- User Story 2: T027–T034 in parallel; T035–T039 follow ingestion pipeline wiring.
- User Story 3: T040–T042, T044, T046 can run in parallel; T043 and T045 align serialization and route integration.

## Implementation Strategy

- MVP first: Complete Setup + Foundational → deliver User Story 1 and validate independently before proceeding.
- Incremental delivery: Add User Story 2 then User Story 3, testing each independently with contract/integration coverage.
- Parallel team: After Phase 2, split teams per story while coordinating shared files to avoid conflicts.
