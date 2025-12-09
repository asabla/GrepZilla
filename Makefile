# ============================================================================
# GrepZilla Makefile
# Common development and Docker operations
# ============================================================================

.PHONY: help install dev test lint format typecheck \
        docker-build docker-up docker-down docker-logs docker-ps \
        docker-shell docker-migrate docker-clean \
        docker-prod-up docker-prod-down

# Default target
.DEFAULT_GOAL := help

# Colors
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RESET := \033[0m

# ============================================================================
# Help
# ============================================================================

help: ## Show this help message
	@echo "$(CYAN)GrepZilla Development Commands$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'

# ============================================================================
# Local Development
# ============================================================================

install: ## Install dependencies using uv
	uv sync

dev: ## Run API server locally with hot-reload
	uv run uvicorn backend.src.api.main:create_app --factory --reload --port 8000

worker: ## Run Celery worker locally
	uv run celery -A backend.src.workers.app worker --loglevel=info

beat: ## Run Celery beat scheduler locally
	uv run celery -A backend.src.workers.app beat --loglevel=info

test: ## Run tests
	uv run pytest

test-cov: ## Run tests with coverage
	uv run pytest --cov=backend --cov-report=html

lint: ## Run linter
	uv run ruff check .

format: ## Format code
	uv run ruff format .

typecheck: ## Run type checker
	uv run mypy backend

migrate: ## Run database migrations locally
	uv run alembic upgrade head

migrate-new: ## Create a new migration (usage: make migrate-new MSG="description")
	uv run alembic revision --autogenerate -m "$(MSG)"

# ============================================================================
# Docker - Development
# ============================================================================

docker-build: ## Build all Docker images
	docker compose build

docker-up: ## Start all services (development mode)
	docker compose up -d

docker-up-logs: ## Start all services with logs attached
	docker compose up

docker-down: ## Stop all services
	docker compose down

docker-restart: ## Restart all services
	docker compose restart

docker-logs: ## View logs for all services (or specify SERVICE=api)
	@if [ -n "$(SERVICE)" ]; then \
		docker compose logs -f $(SERVICE); \
	else \
		docker compose logs -f; \
	fi

docker-ps: ## Show running containers
	docker compose ps

docker-shell: ## Open shell in API container
	docker compose exec api /bin/bash

docker-shell-worker: ## Open shell in worker container
	docker compose exec worker /bin/bash

docker-migrate: ## Run migrations in Docker
	docker compose run --rm migrate

docker-clean: ## Remove all containers, volumes, and images
	docker compose down -v --rmi local

docker-prune: ## Remove unused Docker resources
	docker system prune -f

# ============================================================================
# Docker - Production
# ============================================================================

docker-prod-build: ## Build production images
	docker compose -f docker-compose.yml -f docker-compose.prod.yml build

docker-prod-up: ## Start production stack
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

docker-prod-down: ## Stop production stack
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down

docker-prod-logs: ## View production logs
	@if [ -n "$(SERVICE)" ]; then \
		docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f $(SERVICE); \
	else \
		docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f; \
	fi

# ============================================================================
# Infrastructure Only (for local development without Docker app containers)
# ============================================================================

infra-up: ## Start only infrastructure services (postgres, redis, meilisearch)
	docker compose up -d postgres redis meilisearch

infra-down: ## Stop infrastructure services
	docker compose stop postgres redis meilisearch

# ============================================================================
# Utility
# ============================================================================

redis-cli: ## Open Redis CLI
	docker compose exec redis redis-cli

psql: ## Open PostgreSQL CLI
	docker compose exec postgres psql -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-grepzilla}

env: ## Create .env from example if it doesn't exist
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(GREEN)Created .env from .env.example$(RESET)"; \
	else \
		echo "$(YELLOW).env already exists$(RESET)"; \
	fi
