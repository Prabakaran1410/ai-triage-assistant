from app.models.triage import Citation, Intent
from app.services.escalation import should_escalate

CITATION = Citation(
    source_id="doc-1",
    title="Refund policy",
    updated_at="2026-01-01",
    excerpt="Refunds are processed within 5 business days.",
)


def test_refund_intent_always_escalates():
    escalate, reason = should_escalate(
        intent=Intent.REFUND,
        confidence=0.99,
        citations=[CITATION],
        has_stale_source=False,
    )
    assert escalate is True
    assert "refund" in reason


def test_no_citations_escalates():
    escalate, reason = should_escalate(
        intent=Intent.GENERAL_QUESTION,
        confidence=0.99,
        citations=[],
        has_stale_source=False,
    )
    assert escalate is True
    assert "no citations" in reason


def test_low_confidence_escalates():
    escalate, _ = should_escalate(
        intent=Intent.GENERAL_QUESTION,
        confidence=0.2,
        citations=[CITATION],
        has_stale_source=False,
    )
    assert escalate is True


def test_stale_source_escalates():
    escalate, reason = should_escalate(
        intent=Intent.GENERAL_QUESTION,
        confidence=0.9,
        citations=[CITATION],
        has_stale_source=True,
    )
    assert escalate is True
    assert "stale" in reason


def test_confident_cited_answer_does_not_escalate():
    escalate, reason = should_escalate(
        intent=Intent.GENERAL_QUESTION,
        confidence=0.9,
        citations=[CITATION],
        has_stale_source=False,
    )
    assert escalate is False
    assert reason is None
