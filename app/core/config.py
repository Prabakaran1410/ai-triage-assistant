"""Application settings, loaded from environment variables.

Kept intentionally small in Phase 0. Tenant-specific policy overrides will
layer on top of this once the multi-tenant data model lands.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    # Admin connection - migrations only (scripts/migrate.py). Never used by
    # the running API: it's a superuser/owner role and Postgres does not
    # enforce row-level security against it (see db/migrations/README.md).
    database_url: str = "postgresql+asyncpg://triage:change-me@localhost:5432/triage"

    # Runtime connection - unprivileged `triage_app` role, RLS-enforced.
    # Falls back to database_url only so local dev/tests work before Phase 0's
    # role migration has been run; production must always set this.
    app_database_url: str | None = None

    redis_url: str = "redis://localhost:6379/0"

    llm_provider: str = "anthropic"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None

    oidc_issuer_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None

    langfuse_host: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
