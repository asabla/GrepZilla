#!/bin/bash
# ============================================================================
# GrepZilla Migration Entrypoint
# Waits for dependencies and runs database migrations
# ============================================================================

set -e

# Configuration
MAX_RETRIES=${MAX_RETRIES:-30}
RETRY_INTERVAL=${RETRY_INTERVAL:-2}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ----------------------------------------------------------------------------
# Wait for PostgreSQL
# ----------------------------------------------------------------------------
wait_for_postgres() {
    log_info "Waiting for PostgreSQL..."
    
    # Extract host and port from DATABASE_URL
    # Format: postgresql+asyncpg://user:pass@host:port/db
    DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:]+):([0-9]+)/.*|\1|')
    DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:]+):([0-9]+)/.*|\2|')
    
    if [ -z "$DB_HOST" ] || [ -z "$DB_PORT" ]; then
        log_error "Could not parse DATABASE_URL: $DATABASE_URL"
        exit 1
    fi
    
    retries=0
    until nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; do
        retries=$((retries + 1))
        if [ $retries -ge $MAX_RETRIES ]; then
            log_error "PostgreSQL not available after $MAX_RETRIES attempts"
            exit 1
        fi
        log_warn "PostgreSQL not ready (attempt $retries/$MAX_RETRIES), waiting..."
        sleep $RETRY_INTERVAL
    done
    
    log_info "PostgreSQL is ready at $DB_HOST:$DB_PORT"
}

# ----------------------------------------------------------------------------
# Wait for Redis
# ----------------------------------------------------------------------------
wait_for_redis() {
    log_info "Waiting for Redis..."
    
    # Extract host and port from REDIS_URL
    # Format: redis://host:port/db
    REDIS_HOST=$(echo "$REDIS_URL" | sed -E 's|redis://([^:]+):([0-9]+)/.*|\1|')
    REDIS_PORT=$(echo "$REDIS_URL" | sed -E 's|redis://([^:]+):([0-9]+)/.*|\2|')
    
    if [ -z "$REDIS_HOST" ] || [ -z "$REDIS_PORT" ]; then
        log_warn "Could not parse REDIS_URL, skipping Redis check"
        return 0
    fi
    
    retries=0
    until nc -z "$REDIS_HOST" "$REDIS_PORT" 2>/dev/null; do
        retries=$((retries + 1))
        if [ $retries -ge $MAX_RETRIES ]; then
            log_error "Redis not available after $MAX_RETRIES attempts"
            exit 1
        fi
        log_warn "Redis not ready (attempt $retries/$MAX_RETRIES), waiting..."
        sleep $RETRY_INTERVAL
    done
    
    log_info "Redis is ready at $REDIS_HOST:$REDIS_PORT"
}

# ----------------------------------------------------------------------------
# Wait for Meilisearch
# ----------------------------------------------------------------------------
wait_for_meilisearch() {
    log_info "Waiting for Meilisearch..."
    
    # Extract host from MEILISEARCH_URL
    # Format: http://host:port
    MEILI_URL="${MEILISEARCH_URL:-http://localhost:7700}"
    
    retries=0
    until curl -sf "$MEILI_URL/health" >/dev/null 2>&1; do
        retries=$((retries + 1))
        if [ $retries -ge $MAX_RETRIES ]; then
            log_error "Meilisearch not available after $MAX_RETRIES attempts"
            exit 1
        fi
        log_warn "Meilisearch not ready (attempt $retries/$MAX_RETRIES), waiting..."
        sleep $RETRY_INTERVAL
    done
    
    log_info "Meilisearch is ready at $MEILI_URL"
}

# ----------------------------------------------------------------------------
# Run migrations
# ----------------------------------------------------------------------------
run_migrations() {
    log_info "Running database migrations..."
    
    # Check if alembic.ini exists
    if [ ! -f "/app/alembic.ini" ]; then
        log_warn "alembic.ini not found - skipping migrations"
        log_warn "To enable migrations, create alembic.ini and migrations folder"
        return 0
    fi
    
    # Run alembic migrations (use .venv path if available)
    if [ -f "/app/.venv/bin/alembic" ]; then
        /app/.venv/bin/alembic upgrade head
    else
        alembic upgrade head
    fi
    
    if [ $? -eq 0 ]; then
        log_info "Migrations completed successfully"
    else
        log_error "Migration failed"
        exit 1
    fi
}

# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
main() {
    log_info "Starting GrepZilla migration container"
    
    # Wait for all dependencies
    wait_for_postgres
    wait_for_redis
    wait_for_meilisearch
    
    # Run migrations
    run_migrations
    
    log_info "Migration container finished successfully"
}

main "$@"
