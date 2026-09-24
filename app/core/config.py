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

    # WorkOS handles *who* someone is (SSO against a customer's own IdP).
    # It never manages our tenant/user data - a successful login is
    # exchanged for our own JWT (jwt_secret) that every other endpoint
    # verifies. See app/services/auth.py.
    workos_client_id: str | None = None
    workos_api_key: str | None = None
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_expiry_minutes: int = 60
    # Used to build the SSO redirect_uri (must match what's registered in
    # WorkOS). Render's URL locally would be your ngrok/dev tunnel; in
    # production it's the real API domain.
    app_base_url: str = "http://localhost:8000"

    langfuse_host: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
