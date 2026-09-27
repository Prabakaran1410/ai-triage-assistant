"""Recording triage decisions: the system of record.

Note the deliberate contrast with app/core/tracing.py. Tracing is best-effort
and must never break a request. This is the opposite: if we cannot record what
the system decided, the request fails. For a product whose selling point is an
auditable trail of why each reply was trusted or escalated, answering a
customer with no record of it is the worse outcome - and when the decision was
to escalate, an unrecorded event is one no reviewer will ever see, so the
"answer" would be lost anyway.

Event and audit row are written in one transaction: a decision always arrives
with the log entry explaining where it came from, or not at all.
"""
import datetime as dt
import json
import uuid
from dataclasses import dataclass

from sqlalchemy import text

from app.core.db import tenant_scoped_connection
from app.models.triage import TriageResponse

# Initial states. Anything a human must look at is needs_review; draft_ready
# means the system is willing to answer, not that it may send without review
# (that is a per-tenant policy, decided elsewhere).
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_DRAFT_READY = "draft_ready"

ACTION_TRIAGED = "triaged"


class ReviewError(Exception):
    """A request that must not be applied: unknown id, bad transition, or a
    malformed cursor."""


@dataclass(frozen=True)
class RecordedEvent:
    event_id: str
    status: str


async def record_triage_decision(
    *,
    tenant_id: str,
    message: str,
    channel: str,
    response: TriageResponse,
    requested_by: str | None,
    latency_ms: int,
    model: str | None,
) -> RecordedEvent:
    event_id = str(uuid.uuid4())
    status = STATUS_NEEDS_REVIEW if response.escalate else STATUS_DRAFT_READY
    citations = [c.model_dump() for c in response.citations]

    async with tenant_scoped_connection(tenant_id) as conn:
        await conn.execute(
            text(
                """
                insert into triage_events (
                    id, tenant_id, message, channel, intent, confidence,
                    escalate, escalation_reason, draft_reply, citations,
                    status, requested_by, latency_ms, model
                ) values (
                    :id, :tenant_id, :message, :channel, :intent, :confidence,
                    :escalate, :escalation_reason, :draft_reply, (:citations)::jsonb,
                    :status, :requested_by, :latency_ms, :model
                )
                """
            ),
            {
                "id": event_id,
                "tenant_id": tenant_id,
                "message": message,
                "channel": channel,
                "intent": response.intent.value,
                "confidence": response.confidence,
                "escalate": response.escalate,
                "escalation_reason": response.escalation_reason,
                "draft_reply": response.draft_reply,
                "citations": json.dumps(citations),
                "status": status,
                "requested_by": requested_by,
                "latency_ms": latency_ms,
                "model": model,
            },
        )
        await conn.execute(
            text(
                """
                insert into triage_event_audit (
                    tenant_id, event_id, actor_user_id, action,
                    from_status, to_status, detail
                ) values (
                    :tenant_id, :event_id, :actor_user_id, :action,
                    null, :to_status, (:detail)::jsonb
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "event_id": event_id,
                # The initial decision is made by the system, not a person,
                # even though a user's request triggered it.
                "actor_user_id": None,
                "action": ACTION_TRIAGED,
                "to_status": status,
                "detail": json.dumps(
                    {
                        "escalate": response.escalate,
                        "escalation_reason": response.escalation_reason,
                        "confidence": response.confidence,
                        "intent": response.intent.value,
                        "cited_sources": [c.source_id for c in response.citations],
                        "model": model,
                        "requested_by": requested_by,
                    }
                ),
            },
        )

    return RecordedEvent(event_id=event_id, status=status)


# Which transitions are allowed. Enforced here rather than trusting the
# console: a stale browser tab will happily POST an action against a reply
# somebody else already sent.
STATUS_APPROVED = "approved"
STATUS_EDITED = "edited"
STATUS_SENT = "sent"
STATUS_REJECTED = "rejected"

_OPEN = (STATUS_NEEDS_REVIEW, STATUS_DRAFT_READY)
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "approve": set(_OPEN),
    "edit": set(_OPEN) | {STATUS_APPROVED, STATUS_EDITED},
    "reject": set(_OPEN) | {STATUS_APPROVED, STATUS_EDITED},
    "send": {STATUS_APPROVED, STATUS_EDITED},
}
ACTION_TO_STATUS = {
    "approve": STATUS_APPROVED,
    "edit": STATUS_EDITED,
    "reject": STATUS_REJECTED,
    "send": STATUS_SENT,
}


async def list_events(
    tenant_id: str,
    *,
    status: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[dict], str | None]:
    """A page of the queue, newest first. Keyset pagination on created_at:
    the queue is being worked while it is read, and an OFFSET would skip or
    repeat rows as items change status underneath it."""
    clauses = []
    params: dict = {"limit": limit + 1}
    if status:
        clauses.append("status = :status")
        params["status"] = status
    if cursor:
        # The cursor travels as an opaque ISO string, but asyncpg binds
        # strictly by type and will not coerce it, so parse at the boundary.
        try:
            params["cursor"] = dt.datetime.fromisoformat(cursor)
        except ValueError as e:
            raise ReviewError(f"malformed cursor {cursor!r}") from e
        clauses.append("created_at < :cursor")
    where = f"where {' and '.join(clauses)}" if clauses else ""

    async with tenant_scoped_connection(tenant_id) as conn:
        rows = (
            await conn.execute(
                text(
                    f"""
                    select id, message, intent, confidence, escalate,
                           escalation_reason, status, channel, created_at
                    from triage_events
                    {where}
                    order by created_at desc
                    limit :limit
                    """
                ),
                params,
            )
        ).fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        {
            "id": str(r.id),
            "message": r.message,
            "intent": r.intent,
            "confidence": r.confidence,
            "escalate": r.escalate,
            "escalation_reason": r.escalation_reason,
            "status": r.status,
            "channel": r.channel,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
    next_cursor = rows[-1].created_at.isoformat() if has_more and rows else None
    return items, next_cursor


async def get_event(tenant_id: str, event_id: str) -> dict | None:
    async with tenant_scoped_connection(tenant_id) as conn:
        row = (
            await conn.execute(
                text("select * from triage_events where id = :id"), {"id": event_id}
            )
        ).fetchone()
        if row is None:
            return None
        # Left join so a system action (null actor) still shows up.
        audit = (
            await conn.execute(
                text(
                    """
                    select a.action, a.from_status, a.to_status, a.detail,
                           a.created_at, u.email as actor_email
                    from triage_event_audit a
                    left join users u on u.id = a.actor_user_id
                    where a.event_id = :id
                    order by a.created_at
                    """
                ),
                {"id": event_id},
            )
        ).fetchall()

    return {
        "id": str(row.id),
        "message": row.message,
        "intent": row.intent,
        "confidence": row.confidence,
        "escalate": row.escalate,
        "escalation_reason": row.escalation_reason,
        "draft_reply": row.draft_reply,
        "final_reply": row.final_reply,
        "citations": row.citations,
        "status": row.status,
        "channel": row.channel,
        "model": row.model,
        "latency_ms": row.latency_ms,
        "created_at": row.created_at.isoformat(),
        "audit": [
            {
                "action": a.action,
                "actor_email": a.actor_email,
                "from_status": a.from_status,
                "to_status": a.to_status,
                "detail": a.detail,
                "created_at": a.created_at.isoformat(),
            }
            for a in audit
        ],
    }


async def apply_review(
    *,
    tenant_id: str,
    event_id: str,
    action: str,
    actor_user_id: str,
    final_reply: str | None = None,
    note: str | None = None,
) -> str:
    """Apply a reviewer's decision. Returns the new status.

    The row is locked for the duration so two reviewers opening the same
    queue item cannot both act on it; the second one gets a ReviewError
    rather than silently overwriting the first.
    """
    if action not in ACTION_TO_STATUS:
        raise ReviewError(f"unknown action {action!r}")
    if action == "edit" and not (final_reply or "").strip():
        raise ReviewError("edit requires the rewritten reply")

    new_status = ACTION_TO_STATUS[action]

    async with tenant_scoped_connection(tenant_id) as conn:
        row = (
            await conn.execute(
                text("select status from triage_events where id = :id for update"),
                {"id": event_id},
            )
        ).fetchone()
        if row is None:
            raise ReviewError("no such event")
        if row.status not in ALLOWED_TRANSITIONS[action]:
            raise ReviewError(f"cannot {action} a reply that is already '{row.status}'")

        await conn.execute(
            text(
                """
                update triage_events
                   set status = :status,
                       final_reply = coalesce(:final_reply, final_reply),
                       reviewed_by = :actor,
                       reviewed_at = now()
                 where id = :id
                """
            ),
            {
                "status": new_status,
                "final_reply": final_reply,
                "actor": actor_user_id,
                "id": event_id,
            },
        )
        await conn.execute(
            text(
                """
                insert into triage_event_audit (
                    tenant_id, event_id, actor_user_id, action,
                    from_status, to_status, detail
                ) values (
                    :tenant_id, :event_id, :actor, :action,
                    :from_status, :to_status, (:detail)::jsonb
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "event_id": event_id,
                "actor": actor_user_id,
                "action": action,
                "from_status": row.status,
                "to_status": new_status,
                # The edited text goes in the audit detail as well as the row,
                # so the trail shows what was actually changed and by whom,
                # even if the reply is edited again later.
                "detail": json.dumps(
                    {k: v for k, v in {"note": note, "final_reply": final_reply}.items() if v}
                ),
            },
        )

    return new_status
