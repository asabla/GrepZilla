# GrepZilla

Code-Aware Search and Q&A API that indexes software repositories and answers natural language questions with precise file and line references.

## Overview

GrepZilla continuously ingests code repositories, discovers all files (source code, configs, documentation, PDFs, images), and breaks them into searchable units while preserving file paths and line ranges. Engineers can ask questions like "where do we implement middlewares and how are these configured?" and get answers that explain the behavior and point to exact files and line numbers.

### Key Features

- **Natural Language Q&A** - Ask questions about your codebase and get explanations with file/line citations
- **Multi-Repository Support** - Index up to 50 repositories (up to 5GB each)
- **Continuous Updates** - Stays current via webhooks and scheduled re-indexing
- **Branch-Aware** - Prioritizes default branches, supports explicit branch queries
- **Access Control** - JWT-based per-repository and per-branch permissions

## Requirements

- Python 3.11+
- PostgreSQL 14+
- Meilisearch v1.3+
- Redis 7+
- Git CLI

## Quick Start

### Option A: Docker (Recommended)

The fastest way to get started is using Docker Compose:

```bash
# Copy environment file
cp .env.example .env

# Start all services (with hot-reload for development)
make docker-up

# Or without make:
docker compose up -d
```

This starts:
- **API** at http://localhost:8000
- **PostgreSQL** at localhost:5432
- **Redis** at localhost:6379
- **Redis Insight** (dashboard) at http://localhost:8001
- **Meilisearch** at http://localhost:7700
- **Celery worker** and **beat scheduler**

Migrations run automatically before the API starts.

See [Docker Documentation](#docker) for more details.

### Option B: Local Development

For local development without Docker containers for the app:

#### 1. Install Dependencies

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e ".[dev]"
```

#### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

#### 3. Start Infrastructure

```bash
# Start only infrastructure services
make infra-up

# Or without make:
docker compose up -d postgres meilisearch redis
```

#### 4. Run Migrations

```bash
make migrate

# Or without make:
uv run alembic upgrade head
```

#### 5. Start Services

```bash
# API server (with hot-reload)
make dev

# Celery worker (separate terminal)
make worker

# Celery beat for scheduled tasks (separate terminal)
make beat
```

## Usage

### Connect a Repository

```bash
curl -X POST http://localhost:8000/repositories \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-project", "git_url": "https://github.com/org/repo.git", "default_branch": "main"}'
```

### Ask Questions

```bash
curl -X POST http://localhost:8000/queries \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "How does the authentication middleware work?", "repositories": ["repo-id"]}'
```

### Query Specific Branches

```bash
curl -X POST http://localhost:8000/queries \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What changed?", "repositories": ["repo-id"], "branches": {"repo-id": "feature-branch"}}'
```

## Performance Targets

| Metric | Target |
|--------|--------|
| Query p95 latency | <3s |
| Notification to index | 90% within 10 minutes |
| Scheduled re-index | Every 24 hours |

## Development

```bash
# Run tests
make test

# Run tests with coverage
make test-cov

# Run linter
make lint

# Format code
make format

# Run type checker
make typecheck
```

Or without make:

```bash
uv run pytest
uv run ruff check .
uv run mypy backend
```

## Docker

### Development Mode

Development mode includes hot-reload for the API and worker:

```bash
# Start all services
make docker-up

# View logs
make docker-logs

# View logs for specific service
make docker-logs SERVICE=api

# Open shell in API container
make docker-shell

# Rebuild after dependency changes
make docker-build
make docker-up

# Stop all services
make docker-down

# Clean up (remove volumes and images)
make docker-clean
```

### Production Mode

Production mode uses optimized settings with resource limits:

```bash
# Build and start production stack
make docker-prod-build
make docker-prod-up

# View logs
make docker-prod-logs

# Stop production stack
make docker-prod-down
```

Or without make:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Services and Ports

| Service | Port | Description |
|---------|------|-------------|
| API | 8000 | FastAPI application |
| PostgreSQL | 5432 | Database |
| Redis | 6379 | Celery broker & cache |
| Redis Insight | 8001 | Redis dashboard |
| Meilisearch | 7700 | Search engine |

### Data Persistence

Data is persisted in Docker named volumes:
- `postgres_data` - PostgreSQL database
- `redis_data` - Redis data (if persistence enabled)
- `meilisearch_data` - Meilisearch indexes

### Migration Flow

Migrations run automatically via the `migrate` container before the API and workers start. This container:
1. Waits for PostgreSQL, Redis, and Meilisearch to be healthy
2. Runs `alembic upgrade head`
3. Exits on success (app containers then start)

To run migrations manually:

```bash
make docker-migrate
```

## Architecture

- **FastAPI + Uvicorn** - Async HTTP API
- **Celery + Redis** - Background task processing
- **PostgreSQL** - Repository and query metadata
- **Meilisearch** - Full-text search index
- **Chonkie** - Code chunking and embeddings

## License

MIT License - see [LICENSE](LICENSE) for details.