import datetime as dt
import logging
import time

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.security import CurrentUser, get_current_user
from app.core.tracing import observe, traced_content
from app.models.triage import Citation, Intent, TriageRequest, TriageResponse
from app.services.escalation import STALE_DAYS_THRESHOLD, should_escalate
from app.services.events import record_triage_decision
from app.services.llm import LLMTriageOutput, get_llm_provider
from app.services.redaction import Redaction, redact, restore, unrestored_placeholders
from app.services.retrieval import RetrievedChunk, retrieve_chunks

logger = logging.getLogger(__name__)

router = APIRouter()

TOP_K = 5
LLM_UNAVAILABLE = "LLM provider unavailable"
REDACTION_LEAK = "redacted value could not be restored in the draft"


def _build_citations(
    chunks: list[RetrievedChunk], used_indices: list[int]
) -> list[Citation]:
    """Only trust citation content that came from our own retrieval.

    used_indices are 1-based, chosen by the model from the numbered snippets
    we sent it. An index outside [1, len(chunks)] means the model referenced
    a snippet that doesn't exist - dropped, not trusted, rather than raising,
    since a partial-but-honest citation list is safer than failing the whole
    request over one bad index.
    """
    citations = []
    for i in used_indices:
        if 1 <= i <= len(chunks):
            chunk = chunks[i - 1]
            citations.append(
                Citation(
                    source_id=chunk.source_id,
                    title=chunk.title,
                    updated_at=chunk.updated_at,
                    excerpt=chunk.content[:280],
                )
            )
    return citations


def _has_stale_source(chunks: list[RetrievedChunk], used_indices: list[int]) -> bool:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=STALE_DAYS_THRESHOLD)
    for i in used_indices:
        if 1 <= i <= len(chunks):
            updated_at = dt.datetime.fromisoformat(chunks[i - 1].updated_at)
            if updated_at < cutoff:
                return True
    return False


async def run_triage(request: TriageRequest, tenant_id: str) -> tuple[TriageResponse, str | None]:
    """The pipeline itself. Returns the response and the model that produced
    it (None if no model answered). Deliberately does not persist: the
    evaluation runner calls this directly, and synthetic runs must not write
    into the tenant's real record. Persistence belongs to the endpoint."""
    # Everything downstream of here - the embedding call, the model, the
    # trace - sees placeholders instead of the customer's identifiers. The
    # original text is kept for the escalation rules and for our own record.
    settings = get_settings()
    redaction = (
        redact(request.message)
        if settings.pii_redaction_enabled
        else Redaction(text=request.message, mapping={})
    )
    safe_message = redaction.text

    with observe(
        "retrieval", as_type="retriever", input=traced_content(safe_message)
    ) as retrieval:
        chunks = await retrieve_chunks(tenant_id, safe_message, k=TOP_K)
        # Which chunks came back and how close they were is the first thing
        # to look at when an answer is wrong; neither carries customer text.
        retrieval.update(
            output=[
                {"source_id": c.source_id, "distance": round(c.distance, 4)} for c in chunks
            ],
            metadata={"k": TOP_K, "hits": len(chunks)},
        )

    provider = get_llm_provider()
    try:
        result: LLMTriageOutput
        result, model = await provider.classify_and_draft(
            message=safe_message,
            snippets=[c.content for c in chunks],
        )
    except Exception:
        # The same "escalate instead of guessing" principle applies when the
        # LLM itself is unavailable, not only when it answers with low
        # confidence. A 500 here would tell an integrator "this request
        # failed"; what actually happened is "we can't safely answer this
        # one - a human should", which is a normal, structured outcome.
        logger.exception("LLM provider failed for tenant=%s", tenant_id)
        return (
            TriageResponse(
                intent=Intent.OTHER,
                priority="high",
                confidence=0.0,
                draft_reply=None,
                citations=[],
                escalate=True,
                escalation_reason=LLM_UNAVAILABLE,
            ),
            None,
        )

    citations = _build_citations(chunks, result.used_snippet_indices)
    has_stale_source = _has_stale_source(chunks, result.used_snippet_indices)

    # Put the customer's real details back before anybody reads the draft.
    draft_reply = restore(result.draft_reply, redaction.mapping)
    leftover = unrestored_placeholders(draft_reply)

    escalate, reason = should_escalate(
        intent=result.intent,
        confidence=result.confidence,
        citations=citations,
        has_stale_source=has_stale_source,
        # The rules read the original: they look for the customer's own
        # words, and should not be reasoning about placeholders.
        message=request.message,
    )

    if leftover:
        # A placeholder survived restoration. Sending "[EMAIL_1]" to a
        # customer is worse than asking a person to look, so it goes to a
        # person - and says so, rather than failing quietly.
        logger.error("Unrestored placeholders %s for tenant=%s", leftover, tenant_id)
        escalate, reason = True, REDACTION_LEAK

    return (
        TriageResponse(
            intent=result.intent,
            priority="high" if escalate else "normal",
            confidence=result.confidence,
            draft_reply=draft_reply,
            citations=citations,
            escalate=escalate,
            escalation_reason=reason,
        ),
        model,
    )


@router.post("/triage", response_model=TriageResponse)
async def triage(
    request: TriageRequest, current_user: CurrentUser = Depends(get_current_user)
) -> TriageResponse:
    tenant_id = current_user.tenant_id
    with observe(
        "triage",
        as_type="span",
        input=traced_content(redact(request.message).text),
        metadata={
            "tenant_id": tenant_id,
            "user_id": current_user.user_id,
            "role": current_user.role,
            "channel": request.channel,
        },
    ) as root:
        started = time.perf_counter()
        response, model = await run_triage(request, tenant_id)
        latency_ms = int((time.perf_counter() - started) * 1000)

        # Unlike tracing, this is not best-effort: if the decision cannot be
        # recorded the request fails, because an unrecorded answer defeats
        # the audit trail, and an unrecorded escalation is one no reviewer
        # will ever see. See app/services/events.py.
        recorded = await record_triage_decision(
            tenant_id=tenant_id,
            message=request.message,
            channel=request.channel,
            response=response,
            requested_by=current_user.user_id,
            latency_ms=latency_ms,
            model=model,
        )
        response.event_id = recorded.event_id
        response.status = recorded.status

        root.update(
            output={
                "intent": response.intent.value,
                "confidence": response.confidence,
                "escalate": response.escalate,
                "escalation_reason": response.escalation_reason,
                "cited_sources": [c.source_id for c in response.citations],
                "event_id": recorded.event_id,
            },
            level="WARNING" if response.escalation_reason == LLM_UNAVAILABLE else None,
        )
        return response
