"""Deterministic escalation rules.

These never depend on the model claiming confidence. Any one of these being
true forces escalate=True, regardless of what the classifier/drafter returned.
"""
from app.models.triage import Citation, Intent

MONEY_LEGAL_SAFETY_INTENTS = {Intent.REFUND, Intent.LEGAL_OR_SAFETY}

CONFIDENCE_THRESHOLD = 0.75
STALE_DAYS_THRESHOLD = 180


def should_escalate(
    intent: Intent,
    confidence: float,
    citations: list[Citation],
    has_stale_source: bool,
) -> tuple[bool, str | None]:
    if intent in MONEY_LEGAL_SAFETY_INTENTS:
        return True, f"intent '{intent.value}' always escalates"
    if not citations:
        return True, "no citations found for the answer"
    if confidence < CONFIDENCE_THRESHOLD:
        return True, f"confidence {confidence:.2f} below threshold {CONFIDENCE_THRESHOLD}"
    if has_stale_source:
        return True, "cited source is stale"
    return False, None
