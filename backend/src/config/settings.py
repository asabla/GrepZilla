"""Environment settings configuration for the application."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "GrepZilla"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # Database (PostgreSQL)
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/grepzilla",
        description="PostgreSQL connection URL",
    )
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)

    # Meilisearch
    meilisearch_url: str = Field(
        default="http://localhost:7700",
        description="Meilisearch server URL",
    )
    meilisearch_api_key: SecretStr | None = Field(
        default=None,
        description="Meilisearch master key",
    )
    meilisearch_index_prefix: str = Field(
        default="grepzilla",
        description="Prefix for Meilisearch index names",
    )

    # Redis (for Celery broker)
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for Celery broker",
    )
    redis_result_backend: str = Field(
        default="redis://localhost:6379/1",
        description="Redis URL for Celery result backend",
    )

    # Git Provider
    git_provider_token: SecretStr | None = Field(
        default=None,
        description="Token for Git provider API access",
    )
    git_provider_type: Literal["github", "gitlab", "bitbucket"] = Field(
        default="github",
        description="Git provider type",
    )

    # JWT Authentication
    jwt_secret_key: SecretStr = Field(
        default=SecretStr("change-me-in-production"),
        description="Secret key for JWT token signing",
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=30, ge=1)

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False
    api_workers: int = Field(default=1, ge=1)

    @property
    def sync_database_url(self) -> str:
        """Get synchronous database URL for Alembic migrations."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
