"""Schemas for the review queue and the actions a reviewer can take."""
from pydantic import BaseModel, Field

from app.models.triage import Citation, Intent


class QueueItem(BaseModel):
    """One row of the review queue. Deliberately not the whole record: the
    queue is scanned, so it carries what a reviewer needs to triage their
    own attention, not the full draft and sources."""

    id: str
    message: str
    intent: Intent | None
    confidence: float | None
    escalate: bool
    escalation_reason: str | None
    status: str
    channel: str
    created_at: str


class QueuePage(BaseModel):
    items: list[QueueItem]
    # Keyset pagination rather than an offset: the queue changes while it is
    # being worked, and offsets skip or repeat rows when that happens.
    next_cursor: str | None = None


class AuditEntry(BaseModel):
    action: str
    actor_email: str | None
    from_status: str | None
    to_status: str | None
    detail: dict
    created_at: str


class EventDetail(BaseModel):
    id: str
    message: str
    intent: Intent | None
    confidence: float | None
    escalate: bool
    escalation_reason: str | None
    draft_reply: str | None
    final_reply: str | None
    citations: list[Citation]
    status: str
    channel: str
    model: str | None
    latency_ms: int | None
    created_at: str
    audit: list[AuditEntry]


class ReviewRequest(BaseModel):
    action: str = Field(description="approve | edit | reject | send")
    # Required for `edit`: what the reviewer rewrote the draft to.
    final_reply: str | None = None
    note: str | None = None
