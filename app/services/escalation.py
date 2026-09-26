"""Deterministic escalation rules.

These never depend on the model claiming confidence. Any one of these being
true forces escalate=True, regardless of what the classifier/drafter returned.

Two layers, deliberately:

1. `sensitive_topic()` looks at the customer's own words for legal, safety,
   privacy and fraud language. It does not depend on the model's intent label at
   all. The first evaluation run showed why that matters: a GDPR deletion
   request was labeled `account` by the model, and nothing else in the pipeline
   would have sent it to a person.
2. `should_escalate()` then applies the intent, citation, confidence and
   freshness rules.

The keyword patterns are conservative on purpose. Plain "refund" or "return" is
NOT a trigger: those are usually routine policy questions, and escalating them
sends work to a person that the system can answer. Each pattern is unit-tested
both ways (it fires, and it does not fire on look-alikes such as "issue").
"""
import re

from app.models.triage import Citation, Intent

# Intents that always go to a person. Complaints are here by product policy: an
# unhappy customer should hear from a human, even when a policy answer exists.
HUMAN_ONLY_INTENTS = {Intent.REFUND, Intent.LEGAL_OR_SAFETY, Intent.COMPLAINT}

CONFIDENCE_THRESHOLD = 0.75
STALE_DAYS_THRESHOLD = 180

_SENSITIVE_PATTERNS: dict[str, re.Pattern[str]] = {
    "legal": re.compile(
        r"\b(sue|suing|sued|lawsuit|lawyer|attorney|legal action|chargeback|charge back)\b",
        re.IGNORECASE,
    ),
    "privacy": re.compile(
        r"\b(gdpr|ccpa|personal (?:data|information)|right to be forgotten|"
        r"delete (?:all )?(?:of )?my (?:data|account|information))\b",
        re.IGNORECASE,
    ),
    "safety": re.compile(
        r"\b(injur\w*|hospital|emergency room|burn(?:ed|t|s)?|rash|allergic|"
        r"poison\w*|chok(?:e|ed|ing)|caught fire|exploded|explosion)\b",
        re.IGNORECASE,
    ),
    "fraud": re.compile(
        r"\b(fraud\w*|phish\w*|scam\w*|identity theft)\b|"
        r"\basked (?:me )?for my (?:full )?(?:card number|password|pin|social security)",
        re.IGNORECASE,
    ),
}


def sensitive_topic(message: str) -> str | None:
    """Return a short reason if the message uses legal/safety/privacy/fraud
    language, else None. Independent of any model output."""
    for category, pattern in _SENSITIVE_PATTERNS.items():
        match = pattern.search(message)
        if match:
            return f"message mentions {category} terms ({match.group(0).lower()!r})"
    return None


def should_escalate(
    intent: Intent,
    confidence: float,
    citations: list[Citation],
    has_stale_source: bool,
    message: str | None = None,
) -> tuple[bool, str | None]:
    if message is not None:
        reason = sensitive_topic(message)
        if reason is not None:
            return True, reason
    if intent in HUMAN_ONLY_INTENTS:
        return True, f"intent '{intent.value}' always escalates"
    if not citations:
        return True, "no citations found for the answer"
    if confidence < CONFIDENCE_THRESHOLD:
        return True, f"confidence {confidence:.2f} below threshold {CONFIDENCE_THRESHOLD}"
    if has_stale_source:
        return True, "cited source is stale"
    return False, None
