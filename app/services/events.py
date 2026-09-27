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
