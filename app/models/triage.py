"""Schemas for the /triage endpoint.

Escalation is always computed by rules outside the model (see
app/services/escalation.py) — never by asking the LLM whether it is confident.
"""
from enum import Enum

from pydantic import BaseModel, Field


class Intent(str, Enum):
    BILLING = "billing"
    REFUND = "refund"
    TECHNICAL_ISSUE = "technical_issue"
    ACCOUNT = "account"
    GENERAL_QUESTION = "general_question"
    COMPLAINT = "complaint"
    LEGAL_OR_SAFETY = "legal_or_safety"
    OTHER = "other"


class Citation(BaseModel):
    source_id: str
    title: str
    updated_at: str
    excerpt: str


class TriageRequest(BaseModel):
    # No tenant_id here deliberately: it comes from the verified JWT
    # (app/core/security.py), never from what a caller claims in the body.
    # A client that could set its own tenant_id could read any tenant's
    # knowledge base just by asking.
    message: str = Field(min_length=1)
    channel: str = "api"
    # Where an approved reply would be sent. Optional: a message can arrive
    # without one (a web form, an internal test), which simply means the
    # reply cannot be delivered.
    customer_email: str | None = None


class TriageResponse(BaseModel):
    intent: Intent
    priority: str
    confidence: float = Field(ge=0.0, le=1.0)
    draft_reply: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    escalate: bool
    escalation_reason: str | None = None
    # Set once the decision is recorded, so a caller can refer to it later
    # and a console can link straight to the queue item.
    event_id: str | None = None
    status: str | None = None
