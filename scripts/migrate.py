"""Apply SQL files in db/migrations in order, via a raw asyncpg connection
(not SQLAlchemy) so a migration file's multiple statements run in one simple
query, which the Supabase pooler's transaction mode allows but the prepared-
statement path used elsewhere in the app does not.

No rollback tooling yet - Phase 0 only. Re-run is safe: every statement uses
IF NOT EXISTS / CREATE OR REPLACE where it matters.

Usage: python scripts/migrate.py
Requires DATABASE_URL in the environment (see .env.example), in the
postgresql:// or postgresql+asyncpg:// form.
"""
import asyncio
import os
import pathlib
import sys

import asyncpg

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "db" / "migrations"


def _asyncpg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print("No migrations found.")
        return

    conn = await asyncpg.connect(_asyncpg_dsn(database_url), statement_cache_size=0)
    try:
        for path in files:
            print(f"Applying {path.name} ...")
            sql = path.read_text(encoding="utf-8")
            await conn.execute(sql)
    finally:
        await conn.close()
    print(f"Applied {len(files)} migration(s).")


if __name__ == "__main__":
    asyncio.run(main())
