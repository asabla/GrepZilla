# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GrepZilla is a code-aware search and Q&A API that indexes software repositories and answers natural language questions with precise file and line references. It continuously ingests repositories, discovers all files (source code, configs, documentation, PDFs, images), and breaks them into searchable units while preserving file paths and line ranges.

**Tech Stack**: FastAPI + Uvicorn, Celery + Redis, PostgreSQL, Meilisearch, Chonkie (chunking/embeddings)

## Essential Commands

### Local Development (with Docker infrastructure)

```bash
# Setup
cp .env.example .env          # Configure environment
make infra-up                 # Start infrastructure services only
make migrate                  # Run database migrations

# Development servers (run in separate terminals)
make dev                      # Start API with hot-reload (port 8000)
make worker                   # Start Celery worker
make beat                     # Start Celery beat scheduler

# Testing and quality
make test                     # Run all tests
make test-cov                 # Run tests with coverage report
pytest backend/tests/unit/test_specific.py -v  # Run single test file
pytest backend/tests/unit/test_specific.py::test_name -v  # Run single test

make lint                     # Run ruff linter
make format                   # Format code with ruff
make typecheck                # Run mypy type checker
```

### Docker Development (full stack)

```bash
make docker-up                # Start all services with hot-reload
make docker-logs              # View all logs
make docker-logs SERVICE=api  # View specific service logs
make docker-shell             # Open shell in API container
make docker-down              # Stop all services
make docker-clean             # Remove containers, volumes, images
```

### Database Migrations

```bash
# Local
make migrate                           # Apply migrations
make migrate-new MSG="description"     # Create new migration

# Docker
make docker-migrate                    # Run migrations in Docker
```

Migrations are managed with Alembic and run automatically in Docker via the `migrate` service before the API starts. Migration files are in `backend/src/db/migrations/versions/`.

## Architecture

### Directory Structure

```
backend/
├── src/
│   ├── api/              # FastAPI routes, schemas, middleware
│   │   ├── routes/       # API endpoints (repositories, queries, webhooks)
│   │   ├── schemas/      # Pydantic request/response models
│   │   ├── middleware/   # HTTP middleware (error handling)
│   │   ├── deps/         # Dependencies (auth, database sessions)
│   │   └── main.py       # FastAPI app factory
│   ├── models/           # SQLAlchemy ORM models
│   ├── services/         # Business logic layer
│   │   ├── ai/           # LLM and embedding clients (OpenAI-compatible)
│   │   ├── ingestion/    # Repository ingestion, chunking, indexing
│   │   ├── search/       # Search pipeline and Meilisearch integration
│   │   ├── listing/      # File discovery and filtering
│   │   └── observability/# Metrics and monitoring
│   ├── workers/          # Celery background tasks
│   │   ├── app.py        # Celery app configuration
│   │   └── tasks/        # Task modules (ingestion, scheduling)
│   ├── config/           # Settings, logging, feature flags
│   └── db/               # Database session and migrations
└── tests/
    ├── unit/             # Unit tests
    ├── integration/      # Integration tests
    └── contract/         # API contract tests
```

### Application Flow

**FastAPI App** (`backend/src/api/main.py`):
- Factory pattern with `create_app()` function
- Lifespan context manager handles startup/shutdown
- Routes registered in `_register_routes()`
- Middleware registered in `_register_middleware()`
- Celery app imported on startup to enable task dispatching

**Celery Worker** (`backend/src/workers/app.py`):
- Task autodiscovery configured via `imports=["backend.src.workers.tasks"]`
- Beat schedule defined in `app.conf.beat_schedule` with task names matching `@shared_task(name=...)` decorators
- Tasks organized in `backend/src/workers/tasks/` (ingestion, schedule)
- All tasks must be imported in `backend/src/workers/tasks/__init__.py`

**Ingestion Pipeline**:
1. **Discovery**: `services/listing/` discovers files in repository
2. **Chunking**: `services/ingestion/` breaks files into chunks (Chonkie)
3. **Embedding**: `services/ai/embeddings.py` generates embeddings (OpenAI-compatible API)
4. **Indexing**: `services/ingestion/index_writer.py` writes to Meilisearch

**Search Pipeline** (`services/search/search_pipeline.py`):
1. Branch-aware filtering (default branch prioritized, explicit branch override supported)
2. Hybrid search: text search + vector similarity (if embeddings enabled)
3. LLM-based Q&A with context from top chunks
4. Results include file paths and line ranges

### Database Models

Key models in `backend/src/models/`:
- **Repository**: Tracks Git repositories (name, URL, default branch)
- **Branch**: Tracks branches per repository (name, last commit SHA)
- **Artifact**: Represents files/chunks in the index
- **IndexRecord**: Tracks indexing status per repository/branch
- **Query**: Stores query history and results
- **Notification**: Webhook notifications for repository updates

### Configuration

Settings loaded via Pydantic from environment variables (`backend/src/config/settings.py`):
- Database connection (PostgreSQL via asyncpg)
- Redis URLs (broker and result backend)
- Meilisearch URL and API key
- LLM settings (OpenAI-compatible API: base URL, model, temperature)
- Embedding settings (separate API, model, batch size)
- JWT authentication (secret, algorithm, expiration)

Feature flags in `backend/src/config/feature_flags.py` control experimental features.

## Critical Implementation Patterns

### Celery Task Registration

**IMPORTANT**: Celery tasks MUST be properly registered to avoid "unregistered task" errors.

1. Define tasks with explicit names matching beat schedule:
   ```python
   @shared_task(name="backend.src.workers.tasks.schedule.check_freshness")
   def check_freshness():
       ...
   ```

2. Import tasks in `backend/src/workers/tasks/__init__.py`:
   ```python
   from backend.src.workers.tasks import ingestion, schedule
   ```

3. Verify registration in worker logs:
   ```bash
   docker compose logs worker | grep "[tasks]"
   ```

4. Restart workers after code changes:
   ```bash
   docker compose restart worker beat
   ```

### Database Sessions

- Use async sessions from `backend/src/db/session.py`
- API routes get sessions via dependency injection (`Depends(get_db)`)
- Workers use `get_db_session()` context manager
- Migrations use synchronous connection (psycopg2)

### AI Service Integration

Both LLM and embedding services use OpenAI-compatible APIs (works with OpenAI, Ollama, Azure, etc.):

```python
from backend.src.services.ai import get_llm_client, get_embedding_client

llm = get_llm_client()
response = await llm.generate_answer(query, context_chunks)

embedder = get_embedding_client()
embeddings = await embedder.embed_texts(texts)
```

Configure via `.env`:
- `LLM_API_BASE_URL`: OpenAI, Ollama, or Azure endpoint
- `LLM_MODEL`: Model name (gpt-4o-mini, llama3.2, etc.)
- `EMBEDDING_MODEL`: Embedding model (text-embedding-3-small, nomic-embed-text, etc.)

### Testing Strategy

- **Unit tests**: Test individual functions/classes in isolation
- **Integration tests**: Test services with real database/search interactions
- **Contract tests**: Test API endpoints (request/response schemas)

Run tests with `pytest` or `make test`. Use `-v` for verbose output, `--cov` for coverage.

## Troubleshooting

### "Received unregistered task" Error

This occurs when Celery worker doesn't recognize a task. Check:
1. Task name in `@shared_task(name=...)` matches beat schedule
2. Task module imported in `backend/src/workers/tasks/__init__.py`
3. Worker restarted after code changes: `docker compose restart worker beat`
4. Worker logs show task registered: `docker compose logs worker | grep "[tasks]"`

### Migration Issues

If migrations fail:
1. Check database connection: `make psql`
2. Verify migrations directory exists: `backend/src/db/migrations/versions/`
3. Reset database (DEV ONLY): `docker compose down -v && docker compose up -d`

### Search Returns No Results

1. Verify repository indexed: Check `index_records` table
2. Check Meilisearch index: `curl http://localhost:7700/indexes/grepzilla_chunks/stats`
3. Verify embeddings generated (if enabled): Check `EMBEDDING_ENABLED` in `.env`
4. Check worker logs for ingestion errors: `make docker-logs SERVICE=worker`

## Performance Targets

- Query p95 latency: <3s
- Notification to index: 90% within 10 minutes
- Scheduled re-index: Every 24 hours (configurable in beat schedule)

## Authentication

JWT-based authentication with per-repository and per-branch permissions. All API endpoints (except `/health`) require `Authorization: Bearer <token>` header.
