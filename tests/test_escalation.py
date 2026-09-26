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


# --- keyword guard: independent of the model's intent label -------------------
import pytest

from app.services.escalation import sensitive_topic


@pytest.mark.parametrize(
    "message",
    [
        "I'm going to sue you, the stove burned my hand",
        "I will file a chargeback and call my lawyer",
        "Delete all of my personal data under GDPR",
        "My kid got a rash from the liner",
        "Someone phoned and asked for my card number",
        "This looks like a scam",
    ],
)
def test_sensitive_language_escalates_whatever_the_model_said(message):
    # Even a confident, well-cited, `account`-labeled answer must not go out.
    escalate, reason = should_escalate(
        Intent.ACCOUNT, 1.0, [CITATION], False, message=message
    )
    assert escalate is True and reason.startswith("message mentions")


@pytest.mark.parametrize(
    "message",
    [
        "How many days do I have to return something?",
        "I have an issue with my order",  # 'issue' must not match 'sue'
        "Can I pursue a price adjustment?",  # 'pursue' must not match 'sue'
        "Where is my refund for the boots?",
        "The burner on my stove will not light",  # 'burner' is not 'burned'
        "Do you ship personal items to Canada?",
    ],
)
def test_routine_messages_are_not_caught_by_the_keyword_guard(message):
    assert sensitive_topic(message) is None


def test_complaints_always_go_to_a_person():
    escalate, reason = should_escalate(Intent.COMPLAINT, 1.0, [CITATION], False)
    assert escalate is True and "complaint" in reason
