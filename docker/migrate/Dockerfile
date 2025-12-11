# syntax=docker/dockerfile:1

# ============================================================================
# GrepZilla Migration Dockerfile
# One-shot container for running database migrations
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
    curl \
    netcat-openbsd \
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
# Stage 3: Runtime - final migration image
# ----------------------------------------------------------------------------
FROM base AS runtime

# Copy virtual environment from builder
COPY --from=deps /app/.venv /app/.venv

# Set PATH to use virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code and migration files
COPY backend/ ./backend/

# Copy alembic configuration and migrations
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Copy migration entrypoint script
COPY docker/migrate/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Entrypoint script handles waiting and migrations
ENTRYPOINT ["./entrypoint.sh"]
