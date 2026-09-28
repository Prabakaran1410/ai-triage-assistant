"""The review queue: transitions, audit trail, and who is allowed to act."""
import os
import uuid

import pytest
from sqlalchemy import text

from app.core.db import get_engine, tenant_scoped_connection
from app.models.triage import Citation, Intent, TriageResponse
from app.services.events import (
    STATUS_APPROVED,
    STATUS_EDITED,
    STATUS_NEEDS_REVIEW,
    STATUS_REJECTED,
    STATUS_SENT,
    ReviewError,
    apply_review,
    get_event,
    list_events,
    record_triage_decision,
)

pytestmark = pytest.mark.skipif(
    "APP_DATABASE_URL" not in os.environ,
    reason="requires a live database; set APP_DATABASE_URL to run",
)

class StubProvider:
    name = "stub"

    def __init__(self, fail: bool = False):
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    async def send(self, *, to, subject, body):
        from app.services.delivery import DeliveryError, DeliveryResult

        if self.fail:
            raise DeliveryError("the provider is down")
        self.sent.append((to, body))
        return DeliveryResult(delivered=True, provider=self.name, reference="prov-123")


@pytest.fixture
def delivering(monkeypatch):
    """A channel that works, so the send path can be exercised."""
    provider = StubProvider()
    monkeypatch.setattr("app.services.events.get_delivery_provider", lambda: provider)
    return provider


@pytest.fixture
def failing_delivery(monkeypatch):
    provider = StubProvider(fail=True)
    monkeypatch.setattr("app.services.events.get_delivery_provider", lambda: provider)
    return provider


CITATION = Citation(
    source_id="returns-policy", title="Returns",
    updated_at="2026-09-01T00:00:00+00:00", excerpt="Returns within 60 days.",
)


@pytest.fixture
async def tenant():
    """A tenant with one reviewer, torn down afterwards."""
    tid, uid = str(uuid.uuid4()), str(uuid.uuid4())
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into tenants (id, name) values (:id, :n)"),
            {"id": tid, "n": f"review-test-{tid}"},
        )
    # `users` is under RLS, so it can only be written through a tenant-scoped
    # connection - a bare one has no app.tenant_id and the insert is refused.
    async with tenant_scoped_connection(tid) as conn:
        await conn.execute(
            text("insert into users (id, tenant_id, email, role) values (:i,:t,:e,'reviewer')"),
            {"i": uid, "t": tid, "e": f"reviewer-{uid}@example.com"},
        )
    yield tid, uid
    async with engine.begin() as conn:
        await conn.execute(text("delete from tenants where id = :id"), {"id": tid})


async def _queued(
    tenant_id: str, *, escalate: bool = True, customer_email: str | None = "buyer@example.com"
) -> str:
    recorded = await record_triage_decision(
        tenant_id=tenant_id, message="Where is my order?", channel="api",
        response=TriageResponse(
            intent=Intent.GENERAL_QUESTION, priority="high", confidence=0.8,
            draft_reply="A tracking email is sent within 24 hours.",
            citations=[CITATION], escalate=escalate,
            escalation_reason="intent 'complaint' always escalates" if escalate else None,
        ),
        requested_by=None, latency_ms=100, model="m",
        customer_email=customer_email,
    )
    return recorded.event_id


async def test_queue_lists_newest_first_and_filters_by_status(tenant):
    tenant_id, _ = tenant
    first = await _queued(tenant_id)
    second = await _queued(tenant_id, escalate=False)

    items, _ = await list_events(tenant_id)
    assert [i["id"] for i in items] == [second, first]

    only_review, _ = await list_events(tenant_id, status=STATUS_NEEDS_REVIEW)
    assert [i["id"] for i in only_review] == [first]


async def test_queue_paginates_without_repeating_rows(tenant):
    tenant_id, _ = tenant
    ids = [await _queued(tenant_id) for _ in range(3)]

    page1, cursor = await list_events(tenant_id, limit=2)
    assert len(page1) == 2 and cursor is not None
    page2, _ = await list_events(tenant_id, limit=2, cursor=cursor)
    seen = [i["id"] for i in page1 + page2]
    assert sorted(seen) == sorted(ids), "every row appears exactly once across pages"


async def test_approving_records_who_did_it(tenant):
    tenant_id, reviewer = tenant
    event_id = await _queued(tenant_id)

    assert await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="approve", actor_user_id=reviewer
    ) == STATUS_APPROVED

    event = await get_event(tenant_id, event_id)
    assert event["status"] == STATUS_APPROVED
    actions = [(a["action"], a["from_status"], a["to_status"]) for a in event["audit"]]
    assert actions == [
        ("triaged", None, STATUS_NEEDS_REVIEW),
        ("approve", STATUS_NEEDS_REVIEW, STATUS_APPROVED),
    ]
    assert event["audit"][-1]["actor_email"].startswith("reviewer-")


async def test_editing_stores_the_rewritten_reply_and_keeps_the_original(tenant):
    tenant_id, reviewer = tenant
    event_id = await _queued(tenant_id)
    await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="edit",
        actor_user_id=reviewer, final_reply="Rewritten by a human.",
    )
    event = await get_event(tenant_id, event_id)
    assert event["status"] == STATUS_EDITED
    assert event["final_reply"] == "Rewritten by a human."
    # The model's original draft must survive the edit: comparing the two is
    # how the eval set learns what reviewers keep changing.
    assert event["draft_reply"] == "A tracking email is sent within 24 hours."
    assert event["audit"][-1]["detail"]["final_reply"] == "Rewritten by a human."


async def test_edit_without_replacement_text_is_refused(tenant):
    tenant_id, reviewer = tenant
    event_id = await _queued(tenant_id)
    with pytest.raises(ReviewError, match="requires the rewritten reply"):
        await apply_review(
            tenant_id=tenant_id, event_id=event_id, action="edit",
            actor_user_id=reviewer, final_reply="   ",
        )


async def test_a_reply_cannot_be_acted_on_twice(tenant):
    """Two reviewers with the same queue item open: the second must lose."""
    tenant_id, reviewer = tenant
    event_id = await _queued(tenant_id)
    await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="reject", actor_user_id=reviewer
    )
    with pytest.raises(ReviewError, match="already 'rejected'"):
        await apply_review(
            tenant_id=tenant_id, event_id=event_id, action="approve", actor_user_id=reviewer
        )


async def test_sending_requires_approval_first(tenant, delivering):
    tenant_id, reviewer = tenant
    event_id = await _queued(tenant_id)
    with pytest.raises(ReviewError, match="cannot send"):
        await apply_review(
            tenant_id=tenant_id, event_id=event_id, action="send", actor_user_id=reviewer
        )
    await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="approve", actor_user_id=reviewer
    )
    assert await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="send", actor_user_id=reviewer
    ) == STATUS_SENT


# --- delivery: `sent` must mean it actually left ----------------------------

async def test_a_reply_is_not_marked_sent_when_nothing_was_delivered(tenant):
    """The default provider sends nothing. Recording that as `sent` would put
    a lie in the audit trail - the bug this whole path exists to fix."""
    tenant_id, reviewer = tenant
    event_id = await _queued(tenant_id)
    await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="approve", actor_user_id=reviewer
    )
    with pytest.raises(ReviewError, match="No delivery channel"):
        await apply_review(
            tenant_id=tenant_id, event_id=event_id, action="send", actor_user_id=reviewer
        )
    event = await get_event(tenant_id, event_id)
    assert event["status"] == STATUS_APPROVED, "a failed send must not advance the status"


async def test_a_message_with_no_reply_address_cannot_be_sent(tenant, delivering):
    tenant_id, reviewer = tenant
    event_id = await _queued(tenant_id, customer_email=None)
    await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="approve", actor_user_id=reviewer
    )
    with pytest.raises(ReviewError, match="without a reply address"):
        await apply_review(
            tenant_id=tenant_id, event_id=event_id, action="send", actor_user_id=reviewer
        )


async def test_a_provider_failure_leaves_the_reply_unsent(tenant, failing_delivery):
    tenant_id, reviewer = tenant
    event_id = await _queued(tenant_id)
    await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="approve", actor_user_id=reviewer
    )
    with pytest.raises(ReviewError, match="provider is down"):
        await apply_review(
            tenant_id=tenant_id, event_id=event_id, action="send", actor_user_id=reviewer
        )
    event = await get_event(tenant_id, event_id)
    assert event["status"] == STATUS_APPROVED


async def test_a_successful_send_records_what_was_sent_and_where(tenant, delivering):
    tenant_id, reviewer = tenant
    event_id = await _queued(tenant_id)
    await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="approve", actor_user_id=reviewer
    )
    await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="send", actor_user_id=reviewer
    )

    assert delivering.sent == [
        ("buyer@example.com", "A tracking email is sent within 24 hours.")
    ]
    event = await get_event(tenant_id, event_id)
    assert event["status"] == STATUS_SENT
    # The provider's own id, so someone can match it against their logs when
    # a customer says they never received it.
    assert event["audit"][-1]["detail"]["delivery_reference"] == "prov-123"


async def test_an_edited_reply_is_what_gets_sent(tenant, delivering):
    """Not the model's original draft - the reviewer changed it for a reason."""
    tenant_id, reviewer = tenant
    event_id = await _queued(tenant_id)
    await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="edit",
        actor_user_id=reviewer, final_reply="What a human actually wrote.",
    )
    await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="send", actor_user_id=reviewer
    )
    assert delivering.sent[-1][1] == "What a human actually wrote."


async def test_unknown_event_is_refused(tenant):
    tenant_id, reviewer = tenant
    with pytest.raises(ReviewError, match="no such event"):
        await apply_review(
            tenant_id=tenant_id, event_id=str(uuid.uuid4()),
            action="approve", actor_user_id=reviewer,
        )


async def test_rejected_is_terminal(tenant):
    tenant_id, reviewer = tenant
    event_id = await _queued(tenant_id)
    await apply_review(
        tenant_id=tenant_id, event_id=event_id, action="reject", actor_user_id=reviewer
    )
    event = await get_event(tenant_id, event_id)
    assert event["status"] == STATUS_REJECTED


# --- role enforcement, at the API layer -------------------------------------

def test_an_agent_cannot_review_even_by_calling_the_api_directly():
    """The console hides the buttons; that is not access control."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.auth import issue_jwt

    token = issue_jwt(
        user_id=str(uuid.uuid4()), email="agent@example.com",
        tenant_id=str(uuid.uuid4()), role="agent",
    )
    response = TestClient(app).post(
        f"/events/{uuid.uuid4()}/review",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "cannot review" in response.json()["detail"]


def test_review_endpoints_reject_an_unauthenticated_caller():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    assert client.get("/events").status_code == 401
    assert client.get(f"/events/{uuid.uuid4()}").status_code == 401
    assert client.post(f"/events/{uuid.uuid4()}/review", json={"action": "approve"}).status_code == 401
