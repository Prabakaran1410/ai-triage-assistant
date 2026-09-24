import datetime as dt
import logging

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user
from app.models.triage import Citation, Intent, TriageRequest, TriageResponse
from app.services.escalation import STALE_DAYS_THRESHOLD, should_escalate
from app.services.llm import LLMTriageOutput, get_llm_provider
from app.services.retrieval import RetrievedChunk, retrieve_chunks

logger = logging.getLogger(__name__)

router = APIRouter()

TOP_K = 5


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


@router.post("/triage", response_model=TriageResponse)
async def triage(
    request: TriageRequest, current_user: CurrentUser = Depends(get_current_user)
) -> TriageResponse:
    tenant_id = current_user.tenant_id
    chunks = await retrieve_chunks(tenant_id, request.message, k=TOP_K)

    provider = get_llm_provider()
    try:
        result: LLMTriageOutput = await provider.classify_and_draft(
            message=request.message,
            snippets=[c.content for c in chunks],
        )
    except Exception:
        # The same "escalate instead of guessing" principle applies when the
        # LLM itself is unavailable, not only when it answers with low
        # confidence. A 500 here would tell an integrator "this request
        # failed"; what actually happened is "we can't safely answer this
        # one - a human should", which is a normal, structured outcome.
        logger.exception("LLM provider failed for tenant=%s", tenant_id)
        return TriageResponse(
            intent=Intent.OTHER,
            priority="high",
            confidence=0.0,
            draft_reply=None,
            citations=[],
            escalate=True,
            escalation_reason="LLM provider unavailable",
        )

    citations = _build_citations(chunks, result.used_snippet_indices)
    has_stale_source = _has_stale_source(chunks, result.used_snippet_indices)

    escalate, reason = should_escalate(
        intent=result.intent,
        confidence=result.confidence,
        citations=citations,
        has_stale_source=has_stale_source,
    )

    return TriageResponse(
        intent=result.intent,
        priority="high" if escalate else "normal",
        confidence=result.confidence,
        draft_reply=result.draft_reply,
        citations=citations,
        escalate=escalate,
        escalation_reason=reason,
    )
