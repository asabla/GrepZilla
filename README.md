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

### 1. Install Dependencies

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e ".[dev]"
```

### 2. Configure Environment

Create a `.env` file:

```bash
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/grepzilla
MEILISEARCH_URL=http://localhost:7700
MEILISEARCH_API_KEY=your-master-key
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-secure-secret-key
```

### 3. Start Infrastructure

```bash
docker compose up -d postgres meilisearch redis
```

### 4. Run Migrations

```bash
uv run alembic upgrade head
```

### 5. Start Services

```bash
# API server
uv run uvicorn backend.src.api.main:create_app --factory --reload --port 8000

# Celery worker (separate terminal)
uv run celery -A backend.src.workers.app worker --loglevel=info

# Celery beat for scheduled tasks (separate terminal)
uv run celery -A backend.src.workers.app beat --loglevel=info
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
uv run pytest

# Run linter
uv run ruff check .

# Run type checker
uv run mypy backend
```

## Architecture

- **FastAPI + Uvicorn** - Async HTTP API
- **Celery + Redis** - Background task processing
- **PostgreSQL** - Repository and query metadata
- **Meilisearch** - Full-text search index
- **Chonkie** - Code chunking and embeddings

## License

MIT License - see [LICENSE](LICENSE) for details.