from fastapi import APIRouter

from app.models.triage import Intent, TriageRequest, TriageResponse
from app.services.escalation import should_escalate

router = APIRouter()


@router.post("/triage", response_model=TriageResponse)
async def triage(request: TriageRequest) -> TriageResponse:
    """Placeholder pipeline: classify -> retrieve -> draft -> escalate.

    Retrieval, classification, and drafting are stubbed until Phase 1 lands
    hybrid retrieval and the provider interface. Escalation rules are real
    and already run outside the model.
    """
    intent = Intent.OTHER
    confidence = 0.0
    citations: list = []

    escalate, reason = should_escalate(
        intent=intent,
        confidence=confidence,
        citations=citations,
        has_stale_source=False,
    )

    return TriageResponse(
        intent=intent,
        priority="normal",
        confidence=confidence,
        draft_reply=None,
        citations=citations,
        escalate=escalate,
        escalation_reason=reason,
    )
