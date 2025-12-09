# Quickstart

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Meilisearch v1.3+
- Redis 7+ (for Celery)
- Git CLI (for cloning repositories)
- uv (recommended) or pip

## Environment Setup

### 1. Install Dependencies

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e ".[dev]"
```

### 2. Configure Environment

Create a `.env` file with the following variables:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/grepzilla

# Meilisearch
MEILISEARCH_URL=http://localhost:7700
MEILISEARCH_API_KEY=your-master-key

# Redis (Celery broker)
REDIS_URL=redis://localhost:6379/0

# JWT Authentication
JWT_SECRET_KEY=your-secure-secret-key
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# Git Provider (optional, for private repos)
GIT_PROVIDER_TOKEN=ghp_your_github_token

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### 3. Start Infrastructure

```bash
# Start PostgreSQL, Meilisearch, and Redis
docker compose up -d postgres meilisearch redis

# Or use local services
# Ensure PostgreSQL, Meilisearch, and Redis are running
```

### 4. Initialize Database

```bash
# Run database migrations
uv run alembic upgrade head
```

### 5. Start Services

```bash
# Terminal 1: Start API server
uv run uvicorn backend.src.api.main:create_app --factory --reload --port 8000

# Terminal 2: Start Celery worker
uv run celery -A backend.src.workers.app worker --loglevel=info

# Terminal 3: Start Celery beat (scheduled tasks)
uv run celery -A backend.src.workers.app beat --loglevel=info
```

## Usage

### 1. Connect a Repository

```bash
# Get an access token (development only)
TOKEN=$(curl -s -X POST http://localhost:8000/auth/dev-token | jq -r '.access_token')

# Create a repository
curl -X POST http://localhost:8000/repositories \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-project",
    "git_url": "https://github.com/org/repo.git",
    "default_branch": "main"
  }'
```

### 2. Trigger Indexing

Indexing happens automatically via:
- Webhook notifications (configure in your Git provider)
- Scheduled re-indexing (every 24 hours by default)

Manual refresh:
```bash
curl -X POST http://localhost:8000/repositories/{repo_id}/refresh \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Ask Questions

```bash
curl -X POST http://localhost:8000/queries \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How does the authentication middleware work?",
    "repositories": ["repo-id-here"]
  }'
```

### 4. List Repositories and Status

```bash
curl http://localhost:8000/repositories \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Query with Branch Override

```bash
curl -X POST http://localhost:8000/queries \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What changes are in the feature branch?",
    "repositories": ["repo-id"],
    "branches": {"repo-id": "feature-branch"}
  }'
```

## Configuration

### File Processing

| Setting | Default | Description |
|---------|---------|-------------|
| MAX_FILE_SIZE_BYTES | 25 MB | Files larger than this are cataloged but not indexed |
| CHUNK_SIZE_TOKENS | 512 | Target chunk size for embeddings |
| MAX_CHUNKS_PER_FILE | 1000 | Prevents memory issues with large files |

### Performance Targets

| Metric | Target | Description |
|--------|--------|-------------|
| Query p95 | <3s | 95th percentile query latency |
| Freshness | 90% <10m | 90% of notifications indexed within 10 minutes |
| Re-index | 24h | Scheduled full re-index interval |

### Repository Limits

| Setting | Default | Description |
|---------|---------|-------------|
| MAX_ACTIVE_REPOS | 50 | Maximum repositories to track |
| MAX_REPO_SIZE_GB | 5 GB | Maximum repository size |
| MAX_BRANCHES_PER_REPO | 20 | Maximum tracked branches |

## Troubleshooting

### Common Issues

1. **Meilisearch connection failed**
   - Verify Meilisearch is running: `curl http://localhost:7700/health`
   - Check `MEILISEARCH_URL` and `MEILISEARCH_API_KEY`

2. **Database connection failed**
   - Verify PostgreSQL is running and accepting connections
   - Check `DATABASE_URL` format

3. **Worker not processing tasks**
   - Verify Redis is running: `redis-cli ping`
   - Check Celery worker logs for errors

4. **Authentication errors**
   - Verify `JWT_SECRET_KEY` matches across services
   - Check token expiration

## Notes

- Binary files (images, executables, etc.) are cataloged but not used for text search
- Access control is enforced per repository using JWT claims
- Files >25MB are listed in catalog but not parsed for content search
