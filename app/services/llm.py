"""Provider-agnostic classification + drafting.

Design choice that matters: the model is never trusted to write citation
content itself. It only picks *which* of the numbered snippets we handed it
it actually used (by index); the API then builds citations from our own
retrieval results for those indices. An index the model invents that we
didn't send back is dropped, not trusted - see build_citations() in
app/api/triage.py.
"""
from typing import ClassVar, Protocol, TypeVar

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.tracing import observe, redact
from app.models.triage import Intent

T = TypeVar("T", bound=BaseModel)


class LLMTriageOutput(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    used_snippet_indices: list[int] = Field(default_factory=list)
    draft_reply: str


class LLMProvider(Protocol):
    async def classify_and_draft(
        self, message: str, snippets: list[str]
    ) -> tuple[LLMTriageOutput, str]:
        """Returns the parsed output and the model that produced it (the
        fallback chain means it varies, and an audit record should say
        which model wrote a customer-facing reply)."""
        ...


SYSTEM_PROMPT = """You triage customer messages for a support team.

You are given a customer message and a numbered list of knowledge-base
snippets (numbered from 1). Decide the intent, how confident you are that
the drafted reply is fully supported by the snippets, and write a draft
reply.

Choose exactly one intent:
- billing: charges, payments, declined cards, promo codes, price adjustments, membership fees.
- refund: the customer is asking to get money back now (a refund, a return for a
  refund, cancelling an order for their money). A question about what the return
  or refund POLICY is, is a general_question, not a refund.
- technical_issue: the website, app, checkout or a link is not working.
- account: login, password (including reset emails), email address, two-factor,
  loyalty points, membership status.
- general_question: information about shipping, hours, policies, products, sizing.
- complaint: the customer is unhappy about service or their experience.
- legal_or_safety: legal threats, chargeback threats, injury or product-safety
  concerns, privacy or data-deletion requests, fraud or phishing reports.
- other: sponsorships, spam, unintelligible messages.
If a message fits both refund and legal_or_safety, choose legal_or_safety.

Rules:
- Only use facts that appear in the numbered snippets. Never state a policy,
  price, or promise that is not written in one of them.
- If the snippets don't contain enough to answer, write a short draft that
  says a team member will follow up, and set confidence low.
- used_snippet_indices must list only the numbers of snippets you actually
  relied on. If you used none, return an empty list.
- confidence reflects how well-supported the draft is by the snippets, not
  how well-written it is.
"""


class GeminiProvider:
    """Tries a chain of models, not just one.

    A single model - especially a "-preview" one, which is what's needed
    today because Google's free tier rejects the stable aliases for new API
    keys - is a single point of failure. Google's own 503s here are
    capacity-based and model-specific, not account-wide, so falling through
    to the next model on a transient server error genuinely improves
    availability rather than just retrying the same contended model.
    """

    # gemini-2.5-flash and gemini-2.5-flash-lite are excluded deliberately -
    # confirmed 404 ("no longer available to new users") on a freshly
    # created API key, so they'd waste a fallback slot on every failure.
    MODEL_CHAIN: ClassVar[list[str]] = [
        "gemini-3-flash-preview",
        "gemini-flash-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.7-flash",
        "gemini-3.1-flash-lite",
    ]

    def __init__(self) -> None:
        from google import genai

        settings = get_settings()
        if not settings.google_api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set")
        self._client = genai.Client(api_key=settings.google_api_key)

    async def classify_and_draft(
        self, message: str, snippets: list[str]
    ) -> tuple[LLMTriageOutput, str]:
        numbered = "\n\n".join(f"[{i + 1}] {s}" for i, s in enumerate(snippets))
        prompt = (
            f"{SYSTEM_PROMPT}\n\nSnippets:\n{numbered or '(none provided)'}"
            f"\n\nCustomer message:\n{message}"
        )
        return await self.generate_structured(
            prompt,
            LLMTriageOutput,
            name="gemini-classify-and-draft",
            metadata={"snippets": len(snippets)},
        )

    async def generate_structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        name: str,
        metadata: dict | None = None,
    ) -> tuple[T, str]:
        """Run `prompt` through the model chain and parse the JSON reply as
        `schema`. Returns the parsed value and the model that produced it.
        Shared by the triage call and by the evaluation judge so both get the
        same fallback behaviour and the same tracing."""
        from google.genai import errors, types

        last_error: Exception | None = None
        for attempt, model in enumerate(self.MODEL_CHAIN, start=1):
            # One generation per attempt, so a trace shows the whole fallback
            # chain: which models were tried, which failed and why, which
            # finally answered.
            with observe(
                name,
                as_type="generation",
                model=model,
                input=redact(prompt),
                metadata={"attempt": attempt, **(metadata or {})},
            ) as generation:
                try:
                    response = await self._client.aio.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=schema,
                        ),
                    )
                except (errors.ServerError, errors.ClientError) as e:
                    # ServerError: 503/500-class, the model is overloaded or
                    # briefly down. ClientError: 404 (model not available to
                    # this key/tier), 429, etc. Either way the next model in
                    # the chain is the right move, not a bug in our request.
                    generation.update(
                        level="ERROR", status_message=f"{type(e).__name__}: {str(e)[:200]}"
                    )
                    last_error = e
                    continue

                usage = getattr(response, "usage_metadata", None)
                generation.update(
                    output=redact(response.text),
                    usage_details={
                        "input": getattr(usage, "prompt_token_count", None) or 0,
                        "output": getattr(usage, "candidates_token_count", None) or 0,
                    },
                )
                return schema.model_validate_json(response.text), model

        raise RuntimeError(
            f"All models in the fallback chain failed. Last error: {last_error}"
        ) from last_error


_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        if settings.llm_provider == "gemini":
            _provider = GeminiProvider()
        else:
            raise NotImplementedError(
                f"LLM_PROVIDER={settings.llm_provider!r} has no provider wired up yet"
            )
    return _provider
