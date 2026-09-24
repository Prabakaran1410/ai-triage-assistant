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
    tenant_id: str
    message: str = Field(min_length=1)
    channel: str = "api"


class TriageResponse(BaseModel):
    intent: Intent
    priority: str
    confidence: float = Field(ge=0.0, le=1.0)
    draft_reply: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    escalate: bool
    escalation_reason: str | None = None
