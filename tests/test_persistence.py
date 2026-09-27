"""Persistence and audit behaviour, against a real database.

Skipped when APP_DATABASE_URL is unset (plain `pytest` with no DB). The
append-only test in particular has to run against Postgres: the point is that
the *database* refuses the write, so mocking it would assert nothing.
"""
import os
import uuid

import pytest
from sqlalchemy import text

from app.core.db import get_engine, tenant_scoped_connection
from app.models.triage import Citation, Intent, TriageResponse
from app.services.events import (
    STATUS_DRAFT_READY,
    STATUS_NEEDS_REVIEW,
    record_triage_decision,
)

pytestmark = pytest.mark.skipif(
    "APP_DATABASE_URL" not in os.environ,
    reason="requires a live database; set APP_DATABASE_URL to run",
)

CITATION = Citation(
    source_id="returns-policy",
    title="Returns",
    updated_at="2026-09-01T00:00:00+00:00",
    excerpt="Returns within 60 days.",
)


@pytest.fixture
async def tenant_id():
    tid = str(uuid.uuid4())
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into tenants (id, name) values (:id, :name)"),
            {"id": tid, "name": f"persistence-test-{tid}"},
        )
    yield tid
    async with engine.begin() as conn:
        await conn.execute(text("delete from tenants where id = :id"), {"id": tid})


def _response(*, escalate: bool) -> TriageResponse:
    return TriageResponse(
        intent=Intent.GENERAL_QUESTION,
        priority="high" if escalate else "normal",
        confidence=0.91,
        draft_reply="You can return unused items within 60 days.",
        citations=[CITATION],
        escalate=escalate,
        escalation_reason="intent 'complaint' always escalates" if escalate else None,
    )


async def test_a_decision_is_recorded_with_its_citations(tenant_id):
    recorded = await record_triage_decision(
        tenant_id=tenant_id,
        message="How long do I have to return something?",
        channel="api",
        response=_response(escalate=False),
        requested_by=None,
        latency_ms=1234,
        model="gemini-3-flash-preview",
    )
    assert recorded.status == STATUS_DRAFT_READY

    async with tenant_scoped_connection(tenant_id) as conn:
        row = (
            await conn.execute(
                text("select * from triage_events where id = :id"),
                {"id": recorded.event_id},
            )
        ).fetchone()

    assert row.status == STATUS_DRAFT_READY
    assert row.escalate is False
    assert row.latency_ms == 1234
    assert row.model == "gemini-3-flash-preview"
    # Citations are snapshotted, so the record of what the customer was told
    # survives the knowledge base being edited later.
    assert row.citations[0]["source_id"] == "returns-policy"
    assert row.citations[0]["excerpt"] == "Returns within 60 days."


async def test_an_escalated_decision_lands_in_the_review_queue(tenant_id):
    recorded = await record_triage_decision(
        tenant_id=tenant_id,
        message="This is the third late order. Awful service.",
        channel="api",
        response=_response(escalate=True),
        requested_by=None,
        latency_ms=800,
        model="gemini-3-flash-preview",
    )
    assert recorded.status == STATUS_NEEDS_REVIEW


async def test_every_decision_writes_an_audit_entry(tenant_id):
    recorded = await record_triage_decision(
        tenant_id=tenant_id, message="hello", channel="email",
        response=_response(escalate=True), requested_by=None,
        latency_ms=10, model="gemini-3-flash-preview",
    )
    async with tenant_scoped_connection(tenant_id) as conn:
        rows = (
            await conn.execute(
                text("select * from triage_event_audit where event_id = :id"),
                {"id": recorded.event_id},
            )
        ).fetchall()

    assert len(rows) == 1
    entry = rows[0]
    assert entry.action == "triaged"
    assert entry.from_status is None and entry.to_status == STATUS_NEEDS_REVIEW
    # The initial decision is the system's, not a person's.
    assert entry.actor_user_id is None
    assert entry.detail["escalation_reason"] == "intent 'complaint' always escalates"


async def test_the_audit_log_cannot_be_rewritten_by_the_app_role(tenant_id):
    """The grant, not a convention, is what makes the log immutable."""
    recorded = await record_triage_decision(
        tenant_id=tenant_id, message="hello", channel="api",
        response=_response(escalate=True), requested_by=None,
        latency_ms=10, model="m",
    )
    async with tenant_scoped_connection(tenant_id) as conn:
        with pytest.raises(Exception, match="permission denied|InsufficientPrivilege"):
            await conn.execute(
                text("update triage_event_audit set action = 'tampered' where event_id = :id"),
                {"id": recorded.event_id},
            )
    async with tenant_scoped_connection(tenant_id) as conn:
        with pytest.raises(Exception, match="permission denied|InsufficientPrivilege"):
            await conn.execute(
                text("delete from triage_event_audit where event_id = :id"),
                {"id": recorded.event_id},
            )


async def test_one_tenant_cannot_read_another_tenants_events(tenant_id):
    recorded = await record_triage_decision(
        tenant_id=tenant_id, message="secret", channel="api",
        response=_response(escalate=False), requested_by=None,
        latency_ms=10, model="m",
    )
    other = str(uuid.uuid4())
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into tenants (id, name) values (:id, :name)"),
            {"id": other, "name": f"other-{other}"},
        )
    try:
        async with tenant_scoped_connection(other) as conn:
            events = (await conn.execute(text("select * from triage_events"))).fetchall()
            audit = (await conn.execute(text("select * from triage_event_audit"))).fetchall()
        assert events == [] and audit == [], "RLS must hide another tenant's record"
        async with tenant_scoped_connection(tenant_id) as conn:
            mine = (await conn.execute(text("select id from triage_events"))).fetchall()
        assert [str(r.id) for r in mine] == [recorded.event_id]
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("delete from tenants where id = :id"), {"id": other})
