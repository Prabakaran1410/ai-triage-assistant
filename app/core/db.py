"""Async DB engine and per-request tenant scoping.

Supabase's pooler runs PgBouncer in transaction mode, which does not support
asyncpg's server-side prepared statements. `statement_cache_size=0` disables
them; without it, queries intermittently fail once the pool cycles
connections under load.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.core.config import get_settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """The runtime engine, using the unprivileged `triage_app` role.

    Never falls back silently to the admin `database_url` in a way that could
    ship to production unnoticed: if APP_DATABASE_URL is unset we still run
    (for local dev before the role migration/password is set up) but log
    loudly, because that combination means RLS is not actually enforced.
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.app_database_url
        if url is None:
            import logging

            logging.getLogger(__name__).warning(
                "APP_DATABASE_URL is not set - falling back to the admin "
                "DATABASE_URL. Row-level security is NOT enforced against "
                "that role. Fine for early local dev, never for a deployed "
                "environment. See db/migrations/README.md."
            )
            url = settings.database_url
        _engine = create_async_engine(
            url,
            pool_pre_ping=True,
            connect_args={"statement_cache_size": 0},
        )
    return _engine


async def dispose_engine() -> None:
    """Close the pool and forget the cached engine.

    Called on application shutdown so connections are returned rather than
    dropped (Render stops the container on every deploy), and between tests,
    where each test gets its own event loop but the cached engine would
    otherwise hold connections belonging to a loop that has closed.
    """
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


@asynccontextmanager
async def tenant_scoped_connection(tenant_id: str) -> AsyncIterator[AsyncConnection]:
    """Yield a connection with `app.tenant_id` set for this transaction only.

    Every tenant-scoped query must run through this, never through a raw
    connection — the RLS policies in db/migrations/0001_init.sql depend on
    this session setting to isolate tenants.
    """
    engine = get_engine()
    async with engine.connect() as conn, conn.begin():
        await conn.execute(
            text("select set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )
        # Belt and suspenders alongside db/migrations/0004_extensions_schema.sql:
        # ALTER ROLE ... SET search_path only takes effect for a brand-new
        # backend session, which the Supabase pooler doesn't guarantee on
        # every checkout. Set it explicitly here too, since a pooled
        # connection with the wrong search_path can't find pgvector's
        # `vector` type (Supabase installs it in an "extensions" schema).
        await conn.execute(text("set search_path = public, extensions"))
        yield conn
