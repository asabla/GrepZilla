# syntax=docker/dockerfile:1

# ============================================================================
# GrepZilla Worker Dockerfile
# Multi-stage build for Celery worker and beat scheduler
# ============================================================================

# ----------------------------------------------------------------------------
# Stage 1: Base image with system dependencies
# ----------------------------------------------------------------------------
FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# ----------------------------------------------------------------------------
# Stage 2: Dependencies - install Python deps into a venv
# ----------------------------------------------------------------------------
FROM base AS deps

# Use uv for fast, reproducible installs
ENV UV_LINK_MODE=copy

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Create virtual environment and install production dependencies
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

# ----------------------------------------------------------------------------
# Stage 3: Runtime - final production image
# ----------------------------------------------------------------------------
FROM base AS runtime

# Copy virtual environment from builder
COPY --from=deps /app/.venv /app/.venv

# Set PATH to use virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY backend/ ./backend/

# Create repos directory for git clones
RUN mkdir -p /app/repos

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Health check for Celery worker
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD celery -A backend.src.workers.app inspect ping -d celery@$HOSTNAME || exit 1

# Default command (worker mode)
# Override with beat command in docker-compose for scheduler
CMD ["celery", "-A", "backend.src.workers.app", "worker", "--loglevel=info"]

# ----------------------------------------------------------------------------
# Stage 4: Dev runtime - add dev-only tooling (hot reload)
# ----------------------------------------------------------------------------
FROM runtime AS dev

# Copy uv for installing additional packages
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install watchfiles for autoreload in development
RUN --mount=type=cache,target=/root/.cache/uv uv pip install --python /app/.venv/bin/python watchfiles

# ----------------------------------------------------------------------------
# Stage 5: Default (production) stage
# This remains the default build target to avoid pulling in dev-only tools
# ----------------------------------------------------------------------------
FROM runtime AS final
