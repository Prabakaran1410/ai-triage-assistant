"""Proves row-level security actually isolates tenants, against a real DB.

Skipped automatically when DATABASE_URL isn't set (e.g. plain `pytest` in CI
without a DB). Run with a real Supabase/Postgres URL to exercise it:
  DATABASE_URL=postgresql+asyncpg://... pytest tests/test_tenant_isolation.py
"""
import os
import uuid

import pytest
from sqlalchemy import text

from app.core.db import get_engine, tenant_scoped_connection

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="requires a live database; set DATABASE_URL to run",
)


@pytest.mark.asyncio
async def test_tenant_cannot_see_another_tenants_rows():
    engine = get_engine()
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()

    async with engine.begin() as conn:
        for tenant_id in (tenant_a, tenant_b):
            await conn.execute(
                text("insert into tenants (id, name) values (:id, :name)"),
                {"id": str(tenant_id), "name": f"tenant-{tenant_id}"},
            )

    # The RLS policy's USING clause also gates inserts (no separate WITH
    # CHECK was defined), so seeding tenant A's row must go through the same
    # tenant-scoped path the app uses - a bare connection with no
    # app.tenant_id set is correctly refused by the database.
    async with tenant_scoped_connection(str(tenant_a)) as conn:
        await conn.execute(
            text(
                "insert into triage_events (tenant_id, message, escalate) "
                "values (:tenant_id, 'hello from a', true)"
            ),
            {"tenant_id": str(tenant_a)},
        )

    try:
        async with tenant_scoped_connection(str(tenant_b)) as conn:
            rows = (await conn.execute(text("select * from triage_events"))).fetchall()
        assert rows == [], "tenant B must not see tenant A's rows"

        async with tenant_scoped_connection(str(tenant_a)) as conn:
            rows = (await conn.execute(text("select * from triage_events"))).fetchall()
        assert len(rows) == 1, "tenant A must see its own row"
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("delete from tenants where id in (:a, :b)"),
                {"a": str(tenant_a), "b": str(tenant_b)},
            )
