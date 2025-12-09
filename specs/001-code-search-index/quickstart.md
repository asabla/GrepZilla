# Quickstart

## Prerequisites
- Python 3.11+
- PostgreSQL
- Meilisearch v1.3+
- Redis (for Celery)

## Steps
1. Install deps: `pip install -r requirements.txt` (placeholder).
2. Configure env: DATABASE_URL, MEILISEARCH_URL, REDIS_URL, GIT_PROVIDER_TOKEN.
3. Start services: API (FastAPI/Uvicorn), workers (Celery), Meilisearch, PostgreSQL, Redis.
4. Connect repository: `POST /repositories` with name, git_url, default_branch, auth info.
5. Trigger webhook or wait for schedule to index.
6. Ask a question: `POST /queries` with query text; optionally specify repositories and branch.
7. List scope: `GET /repositories` to view branches, freshness, backlog.

## Notes
- Binaries are cataloged but not used for text answers.
- Access control enforced per repository using stored ACLs and request auth.
- Performance budgets: query p95 <3s; 90% notifications → fresh index <10m; scheduled re-index within configured window.
