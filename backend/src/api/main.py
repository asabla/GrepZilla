"""FastAPI application factory and router registration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.src.config.logging import configure_logging, get_logger
from backend.src.config.settings import get_settings
from backend.src.db.session import close_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown events."""
    logger = get_logger("lifespan")
    logger.info("Starting application")

    # Startup
    yield

    # Shutdown
    logger.info("Shutting down application")
    await close_engine()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    settings = get_settings()

    # Configure logging first
    configure_logging()

    app = FastAPI(
        title="GrepZilla API",
        description="Code-Aware Search and Q&A API",
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    _register_routes(app)

    # Register middleware
    _register_middleware(app)

    return app


def _register_routes(app: FastAPI) -> None:
    """Register API routes with the application.

    Args:
        app: FastAPI application instance.
    """
    from backend.src.api.routes import queries, repositories, webhooks

    app.include_router(
        repositories.router,
        prefix="/repositories",
        tags=["repositories"],
    )
    app.include_router(
        queries.router,
        prefix="/queries",
        tags=["queries"],
    )
    app.include_router(
        webhooks.router,
        prefix="/repositories",
        tags=["webhooks"],
    )

    # Health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Check application health status."""
        return {"status": "healthy"}


def _register_middleware(app: FastAPI) -> None:
    """Register middleware with the application.

    Args:
        app: FastAPI application instance.
    """
    from backend.src.api.middleware.errors import error_handling_middleware

    app.middleware("http")(error_handling_middleware)


# Application instance for ASGI servers
app = create_app()
